from __future__ import annotations

import contextlib
import json
import os
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from typing import Any

from .parsers import (
    normalize_color,
    parse_mega_event_from_log,
    parse_tablet_fault_line,
    parse_vision_event,
    parse_vision_heartbeat,
    parse_vision_status,
    parse_vision_tracks,
)


SHIFT_PRESETS: dict[str, dict[str, str]] = {
    "SHIFT-A": {"name": "A Vardiyasi", "start": "08:00:00", "end": "16:00:00"},
    "SHIFT-B": {"name": "B Vardiyasi", "start": "16:00:00", "end": "00:00:00"},
    "SHIFT-C": {"name": "C Vardiyasi", "start": "00:00:00", "end": "08:00:00"},
}

WORK_ORDER_STATUSES = {"queued", "active", "pending_approval", "completed"}
WORK_ORDER_BLOCKING_STATUSES = {"active", "pending_approval"}
OEE_TREND_INTERVAL_SEC = 30
OEE_TREND_HISTORY_LIMIT = 120
OPERATIONAL_STATES = {
    "idle_ready",
    "opening_checklist",
    "shift_active_running",
    "manual_fault_active",
    "closing_checklist",
}


def empty_color_counts() -> dict[str, int]:
    return {"total": 0, "good": 0, "rework": 0, "scrap": 0}


def shift_options() -> list[dict[str, str]]:
    return [
        {
            "code": code,
            "name": preset["name"],
            "window": f"{preset['start'][:5]} - {preset['end'][:5]}",
        }
        for code, preset in SHIFT_PRESETS.items()
    ]


def default_work_order_state() -> dict[str, Any]:
    return {
        "toleranceMs": 15 * 60 * 1000,
        "toleranceMinutes": 15.0,
        "ordersById": {},
        "orderSequence": [],
        "activeOrderId": "",
        "lastCompletedOrderId": "",
        "lastCompletedAt": "",
        "inventoryByProduct": {},
        "transitionLog": [],
        "completionLog": [],
        "source": {
            "folder": "",
            "file": "",
            "loadedAt": "",
        },
    }


def default_maintenance_state() -> dict[str, Any]:
    return {
        "openingSession": None,
        "closingSession": None,
        "history": [],
        "openingChecklistDurationMs": 0,
        "closingChecklistDurationMs": 0,
        "lastOpeningCompletedAt": "",
        "lastClosingCompletedAt": "",
    }


def default_help_request_state() -> dict[str, Any]:
    return {
        "requestsByKey": {},
        "history": [],
    }


class WorkOrderTransitionReasonRequired(ValueError):
    def __init__(
        self,
        *,
        order_id: str,
        previous_order_id: str,
        elapsed_ms: int,
        tolerance_ms: int,
    ) -> None:
        super().__init__("WORK_ORDER_REASON_REQUIRED")
        self.order_id = order_id
        self.previous_order_id = previous_order_id
        self.elapsed_ms = max(0, int(elapsed_ms))
        self.tolerance_ms = max(0, int(tolerance_ms))
        self.elapsed_minutes = self.elapsed_ms / 60000.0
        self.tolerance_minutes = self.tolerance_ms / 60000.0


def default_runtime_state() -> dict[str, Any]:
    return {
        "version": 5,
        "shiftSelected": "SHIFT-A",
        "performanceMode": "TARGET",
        "targetQty": 14,
        "idealCycleMs": 10_000,
        "idealCycleSec": 10.0,
        "plannedStopMs": 0,
        "plannedStopMin": 0.0,
        "operationalState": "idle_ready",
        "shift": {
            "active": False,
            "code": "",
            "name": "",
            "startedAt": "",
            "endedAt": "",
            "planStart": "",
            "planEnd": "",
            "performanceMode": "TARGET",
            "targetQty": 14,
            "idealCycleMs": 10_000,
            "idealCycleSec": 10.0,
            "plannedStopMs": 0,
            "plannedStopMin": 0.0,
        },
        "counts": {
            "total": 0,
            "good": 0,
            "rework": 0,
            "scrap": 0,
            "byColor": {
                "red": empty_color_counts(),
                "yellow": empty_color_counts(),
                "blue": empty_color_counts(),
            },
        },
        "itemsById": {},
        "queueOrder": [],
        "recentItemIds": [],
        "workOrders": default_work_order_state(),
        "maintenance": default_maintenance_state(),
        "helpRequest": default_help_request_state(),
        "deviceRegistry": {},
        "deviceSessions": {},
        "processedVisionEventKeys": [],
        "activeFault": None,
        "faultHistory": [],
        "unplannedDowntimeMs": 0,
        "manualFaultDurationMs": 0,
        "trend": [],
        "qualityOverrideLog": [],
        "qualityOverrideResetAt": "",
        "earlyPickRejectLog": [],
        "vision": {
            "healthState": "offline",
            "badWindows": 0,
            "goodWindows": 0,
            "fps": 0.0,
            "eventLatencyMs": None,
            "lastStatusAt": "",
            "lastTracksAt": "",
            "lastHeartbeatAt": "",
            "lastEventAt": "",
            "lastObservedAt": "",
            "lastPublishedAt": "",
            "lastReceivedAt": "",
            "lastRejectReason": "",
            "metrics": {
                "mismatchCount": 0,
                "earlyAcceptedCount": 0,
                "earlyRejectedCount": 0,
                "lateAuditCount": 0,
            },
        },
        "lastSnapshotLoggedAt": "",
        "lastEventSummary": "Vardiya secimi bekleniyor.",
        "lastTabletLine": "",
        "lastUpdatedAt": "",
    }


def _numeric(value: Any) -> float:
    text = str(value or "").replace(",", ".").strip()
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _duration_ms(value: Any, *, multiplier: float = 1.0, default: int = 0) -> int:
    normalized = _first_present(value)
    if normalized in (None, ""):
        return max(0, default)
    return max(0, round(_numeric(normalized) * multiplier))


def _first_positive_duration_ms(*candidates: tuple[Any, float], default: int = 0) -> int:
    for value, multiplier in candidates:
        if value in (None, ""):
            continue
        duration_ms = _duration_ms(value, multiplier=multiplier)
        if duration_ms > 0:
            return duration_ms
    return max(0, default)


def _seconds_from_ms(value: Any, *, precision: int = 3) -> float:
    return round(max(0.0, _numeric(value)) / 1000.0, precision)


def _minutes_from_ms(value: Any, *, precision: int = 3) -> float:
    return round(max(0.0, _numeric(value)) / 60000.0, precision)


def _parse_clock(value: str) -> tuple[int, int, int]:
    parts = str(value or "00:00:00").split(":")
    try:
        hour = int(parts[0])
    except (IndexError, ValueError):
        hour = 0
    try:
        minute = int(parts[1])
    except (IndexError, ValueError):
        minute = 0
    try:
        second = int(parts[2])
    except (IndexError, ValueError):
        second = 0
    return hour, minute, second


def _local_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.astimezone()


def _pseudo_iso_text(value: datetime) -> str:
    base = _local_datetime(value) or datetime.now().astimezone()
    return base.astimezone().isoformat(timespec="milliseconds")


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _duration_between_texts(start_text: Any, end_text: Any) -> int:
    start_dt = _parse_iso(str(start_text or ""))
    end_dt = _parse_iso(str(end_text or ""))
    if start_dt is None or end_dt is None:
        return 0
    if start_dt.tzinfo is None:
        start_dt = start_dt.astimezone()
    if end_dt.tzinfo is None:
        end_dt = end_dt.astimezone()
    if end_dt < start_dt:
        return 0
    return max(0, int((end_dt - start_dt).total_seconds() * 1000))


def _short_time(value: str) -> str:
    if not value:
        return "-"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return "-"
    return parsed.astimezone().strftime("%H:%M:%S.%f")[:-3]


def _full_time(value: str) -> str:
    if not value:
        return "-"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return "-"
    return parsed.astimezone().strftime("%d.%m.%Y %H:%M:%S.%f")[:-3]


def _merge_clock_with_stamp(time_text: str | None, stamp: str) -> str:
    base = _parse_iso(stamp)
    if base is None:
        return stamp
    if not time_text:
        return stamp
    hour, minute, second = _parse_clock(str(time_text))
    merged = base.replace(hour=hour, minute=minute, second=second, microsecond=0)
    return _pseudo_iso_text(merged)


def _shift_window(code: str, now: datetime) -> tuple[datetime, datetime, dict[str, str]]:
    preset = SHIFT_PRESETS.get(code, SHIFT_PRESETS["SHIFT-A"])
    start_hour, start_minute, start_second = _parse_clock(preset["start"])
    end_hour, end_minute, end_second = _parse_clock(preset["end"])
    start = now.replace(hour=start_hour, minute=start_minute, second=start_second, microsecond=0)
    end = now.replace(hour=end_hour, minute=end_minute, second=end_second, microsecond=0)
    if end <= start:
        end = end + timedelta(days=1)
    return start, end, preset


def _touch_shift_config(state: dict[str, Any]) -> None:
    shift = state["shift"]
    if not shift.get("active"):
        return
    shift["performanceMode"] = state["performanceMode"]
    shift["targetQty"] = state["targetQty"]
    shift["idealCycleMs"] = state["idealCycleMs"]
    shift["idealCycleSec"] = state["idealCycleSec"]
    shift["plannedStopMs"] = state["plannedStopMs"]
    shift["plannedStopMin"] = state["plannedStopMin"]


def _device_request_key(device_id: Any, bound_station_id: Any) -> str:
    normalized_device_id = str(device_id or "").strip()
    normalized_station_id = str(bound_station_id or "").strip()
    return f"{normalized_device_id}:{normalized_station_id}"


def _normalize_checklist_step(raw: Any, *, fallback_code: str, fallback_label: str = "") -> dict[str, Any]:
    row = raw if isinstance(raw, dict) else {}
    step_code = str(
        row.get("stepCode")
        or row.get("step_code")
        or row.get("maintenance_step_code")
        or fallback_code
    ).strip() or fallback_code
    step_label = str(
        row.get("stepLabel")
        or row.get("step_label")
        or row.get("step_name_tr")
        or fallback_label
        or step_code
    ).strip() or step_code
    return {
        "stepCode": step_code,
        "stepLabel": step_label,
        "required": bool(row.get("required", row.get("is_required", True))),
        "completed": bool(row.get("completed")),
        "completedAt": str(row.get("completedAt") or row.get("completed_at") or ""),
    }


def _normalize_maintenance_session(raw: Any, *, phase: str) -> dict[str, Any]:
    session = raw if isinstance(raw, dict) else {}
    raw_steps = session.get("steps") if isinstance(session.get("steps"), list) else []
    normalized_steps: list[dict[str, Any]] = []
    for index, step in enumerate(raw_steps, start=1):
        normalized_steps.append(
            _normalize_checklist_step(
                step,
                fallback_code=f"{phase}_step_{index}",
                fallback_label=f"{phase.title()} Step {index}",
            )
        )
    return {
        "sessionId": str(session.get("sessionId") or session.get("session_id") or ""),
        "phase": phase,
        "status": str(session.get("status") or "active"),
        "deviceId": str(session.get("deviceId") or session.get("device_id") or ""),
        "deviceName": str(session.get("deviceName") or session.get("device_name") or ""),
        "deviceRole": str(session.get("deviceRole") or session.get("device_role") or "operator_kiosk"),
        "boundStationId": str(session.get("boundStationId") or session.get("bound_station_id") or ""),
        "operatorId": str(session.get("operatorId") or session.get("operator_id") or ""),
        "operatorCode": str(session.get("operatorCode") or session.get("operator_code") or ""),
        "operatorName": str(session.get("operatorName") or session.get("operator_name") or ""),
        "shiftCode": str(session.get("shiftCode") or session.get("shift_code") or ""),
        "startedAt": str(session.get("startedAt") or session.get("started_at") or ""),
        "endedAt": str(session.get("endedAt") or session.get("ended_at") or ""),
        "durationMs": max(0, round(_numeric(session.get("durationMs") or session.get("duration_ms")))),
        "note": str(session.get("note") or ""),
        "steps": normalized_steps,
    }


def _normalize_help_request_row(raw: Any) -> dict[str, Any]:
    row = raw if isinstance(raw, dict) else {}
    response_duration_ms = _duration_ms(
        _first_present(row.get("responseDurationMs"), row.get("response_duration_ms"))
    )
    repair_duration_ms = _duration_ms(
        _first_present(row.get("repairDurationMs"), row.get("repair_duration_ms"))
    )
    total_duration_ms = _duration_ms(
        _first_present(row.get("totalDurationMs"), row.get("total_duration_ms"))
    )
    return {
        "requestId": str(row.get("requestId") or row.get("request_id") or ""),
        "requestKey": str(row.get("requestKey") or row.get("request_key") or ""),
        "lineId": str(row.get("lineId") or row.get("line_id") or ""),
        "deviceId": str(row.get("deviceId") or row.get("device_id") or ""),
        "deviceName": str(row.get("deviceName") or row.get("device_name") or ""),
        "boundStationId": str(row.get("boundStationId") or row.get("bound_station_id") or ""),
        "stationName": str(row.get("stationName") or row.get("station_name") or ""),
        "operatorId": str(row.get("operatorId") or row.get("operator_id") or ""),
        "operatorCode": str(row.get("operatorCode") or row.get("operator_code") or ""),
        "operatorName": str(row.get("operatorName") or row.get("operator_name") or ""),
        "status": str(row.get("status") or "open"),
        "repeatCount": max(1, round(_numeric(row.get("repeatCount") or row.get("repeat_count") or 1))),
        "faultId": str(row.get("faultId") or row.get("fault_id") or ""),
        "faultCode": str(row.get("faultCode") or row.get("fault_code") or row.get("reasonCode") or ""),
        "reason": str(row.get("reason") or row.get("fault_reason") or ""),
        "faultStartedAt": str(row.get("faultStartedAt") or row.get("fault_started_at") or ""),
        "createdAt": str(row.get("createdAt") or row.get("created_at") or ""),
        "lastRequestedAt": str(row.get("lastRequestedAt") or row.get("last_requested_at") or ""),
        "acknowledgedAt": str(row.get("acknowledgedAt") or row.get("acknowledged_at") or ""),
        "resolvedAt": str(row.get("resolvedAt") or row.get("resolved_at") or ""),
        "technicianName": str(row.get("technicianName") or row.get("technician_name") or ""),
        "responseDurationMs": response_duration_ms,
        "repairDurationMs": repair_duration_ms,
        "totalDurationMs": total_duration_ms,
    }


def _normalize_device_registry_entry(raw: Any, *, device_id: str) -> dict[str, Any]:
    row = raw if isinstance(raw, dict) else {}
    return {
        "deviceId": device_id,
        "deviceName": str(row.get("deviceName") or row.get("device_name") or device_id),
        "deviceRole": str(row.get("deviceRole") or row.get("device_role") or "operator_kiosk"),
        "boundStationId": str(row.get("boundStationId") or row.get("bound_station_id") or ""),
        "lastOperatorId": str(row.get("lastOperatorId") or row.get("last_operator_id") or ""),
        "lastSeenAt": str(row.get("lastSeenAt") or row.get("last_seen_at") or ""),
    }


def _normalize_device_session_entry(raw: Any, *, device_id: str) -> dict[str, Any]:
    row = raw if isinstance(raw, dict) else {}
    return {
        "deviceId": device_id,
        "operatorId": str(row.get("operatorId") or row.get("operator_id") or ""),
        "operatorCode": str(row.get("operatorCode") or row.get("operator_code") or ""),
        "operatorName": str(row.get("operatorName") or row.get("operator_name") or ""),
        "boundStationId": str(row.get("boundStationId") or row.get("bound_station_id") or ""),
        "lastSeenAt": str(row.get("lastSeenAt") or row.get("last_seen_at") or ""),
    }


def _normalize_fault_row(raw: Any) -> dict[str, Any]:
    row = raw if isinstance(raw, dict) else {}
    duration_ms = _duration_ms(
        _first_present(
            row.get("durationMs"),
            row.get("duration_ms"),
        ),
        default=_duration_ms(
            _first_present(
                row.get("durationMin"),
                row.get("duration_min"),
            ),
            multiplier=60_000.0,
        ),
    )
    return {
        "faultId": str(row.get("faultId") or row.get("fault_id") or ""),
        "category": str(row.get("category") or row.get("fault_category") or "BILINMIYOR"),
        "reasonCode": str(row.get("reasonCode") or row.get("faultTypeCode") or row.get("fault_type_code") or ""),
        "reason": str(row.get("reason") or row.get("fault_reason_tr") or "Bilinmiyor"),
        "status": str(row.get("status") or row.get("status_code") or ""),
        "startedAt": str(row.get("startedAt") or row.get("started_at") or ""),
        "endedAt": str(row.get("endedAt") or row.get("ended_at") or ""),
        "durationMs": duration_ms,
        "durationMin": _minutes_from_ms(duration_ms, precision=3),
        "source": str(row.get("source") or row.get("source_code") or ""),
        "deviceId": str(row.get("deviceId") or row.get("device_id") or ""),
        "deviceName": str(row.get("deviceName") or row.get("device_name") or ""),
        "operatorId": str(row.get("operatorId") or row.get("operator_id") or ""),
        "operatorCode": str(row.get("operatorCode") or row.get("operator_code") or ""),
        "operatorName": str(row.get("operatorName") or row.get("operator_name") or ""),
        "boundStationId": str(row.get("boundStationId") or row.get("bound_station_id") or ""),
        "countsTowardUnplanned": bool(row.get("countsTowardUnplanned", True)),
    }


def _maintenance_state(state: dict[str, Any]) -> dict[str, Any]:
    maintenance = state.get("maintenance")
    if not isinstance(maintenance, dict):
        maintenance = default_maintenance_state()
        state["maintenance"] = maintenance
    maintenance["openingSession"] = (
        _normalize_maintenance_session(maintenance.get("openingSession"), phase="opening")
        if isinstance(maintenance.get("openingSession"), dict)
        else None
    )
    maintenance["closingSession"] = (
        _normalize_maintenance_session(maintenance.get("closingSession"), phase="closing")
        if isinstance(maintenance.get("closingSession"), dict)
        else None
    )
    history = maintenance.get("history") if isinstance(maintenance.get("history"), list) else []
    normalized_history: list[dict[str, Any]] = []
    for row in history:
        if not isinstance(row, dict):
            continue
        phase = str(row.get("phase") or "opening").strip().lower()
        normalized_history.append(_normalize_maintenance_session(row, phase="closing" if phase == "closing" else "opening"))
    maintenance["history"] = normalized_history[:50]
    maintenance["openingChecklistDurationMs"] = max(0, round(_numeric(maintenance.get("openingChecklistDurationMs"))))
    maintenance["closingChecklistDurationMs"] = max(0, round(_numeric(maintenance.get("closingChecklistDurationMs"))))
    maintenance["lastOpeningCompletedAt"] = str(maintenance.get("lastOpeningCompletedAt") or "")
    maintenance["lastClosingCompletedAt"] = str(maintenance.get("lastClosingCompletedAt") or "")
    return maintenance


def _help_request_state(state: dict[str, Any]) -> dict[str, Any]:
    help_request = state.get("helpRequest")
    if not isinstance(help_request, dict):
        help_request = default_help_request_state()
        state["helpRequest"] = help_request
    requests = help_request.get("requestsByKey") if isinstance(help_request.get("requestsByKey"), dict) else {}
    help_request["requestsByKey"] = {
        key: _normalize_help_request_row(value)
        for key, value in requests.items()
        if str(key or "").strip()
    }
    history = help_request.get("history") if isinstance(help_request.get("history"), list) else []
    help_request["history"] = [
        _normalize_help_request_row(row)
        for row in history
        if isinstance(row, dict)
    ][:50]
    return help_request


def _find_help_request_by_id(help_request: dict[str, Any], request_id: Any) -> tuple[str, dict[str, Any]] | None:
    normalized_request_id = str(request_id or "").strip()
    if not normalized_request_id:
        return None
    requests = help_request.get("requestsByKey") if isinstance(help_request.get("requestsByKey"), dict) else {}
    for request_key, request in requests.items():
        if not isinstance(request, dict):
            continue
        if str(request.get("requestId") or "").strip() == normalized_request_id:
            return str(request_key or ""), request
    return None


def _device_registry_state(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    registry = state.get("deviceRegistry")
    if not isinstance(registry, dict):
        registry = {}
        state["deviceRegistry"] = registry
    normalized: dict[str, dict[str, Any]] = {}
    for raw_key, raw_value in registry.items():
        device_id = str(raw_key or "").strip()
        if not device_id:
            continue
        normalized[device_id] = _normalize_device_registry_entry(raw_value, device_id=device_id)
    state["deviceRegistry"] = normalized
    return normalized


def _device_sessions_state(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    sessions = state.get("deviceSessions")
    if not isinstance(sessions, dict):
        sessions = {}
        state["deviceSessions"] = sessions
    normalized: dict[str, dict[str, Any]] = {}
    for raw_key, raw_value in sessions.items():
        device_id = str(raw_key or "").strip()
        if not device_id:
            continue
        normalized[device_id] = _normalize_device_session_entry(raw_value, device_id=device_id)
    state["deviceSessions"] = normalized
    return normalized


def _active_maintenance_session(state: dict[str, Any], phase: str | None = None) -> dict[str, Any] | None:
    maintenance = _maintenance_state(state)
    if phase == "opening":
        return maintenance.get("openingSession") if isinstance(maintenance.get("openingSession"), dict) else None
    if phase == "closing":
        return maintenance.get("closingSession") if isinstance(maintenance.get("closingSession"), dict) else None
    for candidate in (maintenance.get("openingSession"), maintenance.get("closingSession")):
        if isinstance(candidate, dict):
            return candidate
    return None


def _maintenance_session_duration_ms(session: dict[str, Any], *, now: datetime | None = None) -> int:
    if not isinstance(session, dict):
        return 0
    ended_at = _parse_iso(str(session.get("endedAt") or ""))
    started_at = _parse_iso(str(session.get("startedAt") or ""))
    if started_at is None:
        return max(0, round(_numeric(session.get("durationMs"))))
    end_dt = ended_at or now or datetime.now().astimezone()
    if end_dt.tzinfo is None:
        end_dt = end_dt.astimezone()
    if end_dt < started_at:
        return max(0, round(_numeric(session.get("durationMs"))))
    return max(0, int((end_dt - started_at).total_seconds() * 1000))


def _active_planned_maintenance_ms(state: dict[str, Any], *, now: datetime) -> int:
    session = _active_maintenance_session(state, phase="closing")
    if not isinstance(session, dict):
        return 0
    return _maintenance_session_duration_ms(session, now=now)


def _active_fault_duration_ms(state: dict[str, Any], *, now: datetime) -> int:
    active_fault = state.get("activeFault") if isinstance(state.get("activeFault"), dict) else None
    if not isinstance(active_fault, dict):
        return 0
    if not bool(active_fault.get("countsTowardUnplanned", True)):
        return 0
    started_at = _parse_iso(str(active_fault.get("startedAt") or ""))
    if started_at is None:
        return 0
    if now < started_at:
        return 0
    return max(0, int((now - started_at).total_seconds() * 1000))


def _refresh_operational_state(state: dict[str, Any]) -> str:
    next_state = "idle_ready"
    if isinstance(_active_maintenance_session(state, phase="opening"), dict):
        next_state = "opening_checklist"
    elif isinstance(_active_maintenance_session(state, phase="closing"), dict):
        next_state = "closing_checklist"
    elif isinstance(state.get("activeFault"), dict) and str((state.get("activeFault") or {}).get("source") or "").strip().lower() == "kiosk":
        next_state = "manual_fault_active"
    elif bool(((state.get("shift") or {}) if isinstance(state.get("shift"), dict) else {}).get("active")):
        next_state = "shift_active_running"
    state["operationalState"] = next_state if next_state in OPERATIONAL_STATES else "idle_ready"
    return state["operationalState"]


def _update_device_presence(
    state: dict[str, Any],
    *,
    device_id: str,
    device_name: str = "",
    device_role: str = "",
    bound_station_id: str = "",
    operator_id: str = "",
    operator_code: str = "",
    operator_name: str = "",
    seen_at: str,
) -> None:
    normalized_device_id = str(device_id or "").strip()
    if not normalized_device_id:
        return
    registry = _device_registry_state(state)
    sessions = _device_sessions_state(state)
    entry = registry.get(normalized_device_id, _normalize_device_registry_entry({}, device_id=normalized_device_id))
    if str(device_name or "").strip():
        entry["deviceName"] = str(device_name).strip()
    if str(device_role or "").strip():
        entry["deviceRole"] = str(device_role).strip()
    if str(bound_station_id or "").strip():
        entry["boundStationId"] = str(bound_station_id).strip()
    if str(operator_id or "").strip():
        entry["lastOperatorId"] = str(operator_id).strip()
    entry["lastSeenAt"] = seen_at
    registry[normalized_device_id] = entry
    session = sessions.get(normalized_device_id, _normalize_device_session_entry({}, device_id=normalized_device_id))
    session["boundStationId"] = entry["boundStationId"]
    session["operatorId"] = str(operator_id or session.get("operatorId") or "").strip()
    session["operatorCode"] = str(operator_code or session.get("operatorCode") or "").strip()
    session["operatorName"] = str(operator_name or session.get("operatorName") or "").strip()
    session["lastSeenAt"] = seen_at
    sessions[normalized_device_id] = session


def _text_or_default(value: Any, default: str = "") -> str:
    return str(value or "").strip() or default


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "evet", "e"}


def _normalize_order_color(value: Any, *fallbacks: Any) -> str:
    candidates = (value,) + fallbacks
    for candidate in candidates:
        text = str(candidate or "").strip()
        if not text:
            continue
        normalized = normalize_color(text)
        if normalized in {"red", "yellow", "blue"}:
            return normalized
        upper = text.upper()
        if "RED" in upper or "KIRMIZI" in upper:
            return "red"
        if "YELLOW" in upper or "SARI" in upper:
            return "yellow"
        if "BLUE" in upper or "MAVI" in upper:
            return "blue"
    return ""


def _order_match_key(order: dict[str, Any]) -> str:
    requirements = order.get("requirements") if isinstance(order.get("requirements"), list) else []
    if len(requirements) == 1 and isinstance(requirements[0], dict):
        return (
            str(requirements[0].get("matchKey") or "").strip()
            or str(requirements[0].get("color") or "").strip().lower()
            or str(requirements[0].get("productCode") or "").strip()
            or str(requirements[0].get("stockCode") or "").strip()
        )
    return (
        str(order.get("matchKey") or "").strip()
        or str(order.get("productColor") or "").strip().lower()
        or str(order.get("productCode") or "").strip()
        or str(order.get("stockCode") or "").strip()
    )


def _normalize_inventory_row(raw: Any, match_key: str = "") -> dict[str, Any]:
    entry = raw if isinstance(raw, dict) else {}
    item_ids_raw = entry.get("itemIds") if isinstance(entry.get("itemIds"), list) else entry.get("item_ids")
    item_ids: list[str] = []
    seen_item_ids: set[str] = set()
    if isinstance(item_ids_raw, list):
        for raw_item_id in item_ids_raw:
            item_id = str(raw_item_id or "").strip()
            if not item_id or item_id in seen_item_ids:
                continue
            item_ids.append(item_id)
            seen_item_ids.add(item_id)
    color = _normalize_order_color(
        entry.get("color"),
        entry.get("productColor"),
        entry.get("stockCode"),
        entry.get("stockName"),
    )
    resolved_match_key = str(entry.get("matchKey") or "").strip() or match_key or color or str(entry.get("productCode") or entry.get("stockCode") or "").strip()
    quantity = max(0, round(_numeric(entry.get("quantity") or entry.get("availableQty") or 0)))
    return {
        "matchKey": resolved_match_key,
        "productCode": _text_or_default(entry.get("productCode") or entry.get("stockCode"), resolved_match_key),
        "stockCode": _text_or_default(entry.get("stockCode") or entry.get("productCode"), resolved_match_key),
        "stockName": _text_or_default(entry.get("stockName"), resolved_match_key or color or "Urun"),
        "color": color,
        "quantity": max(quantity, len(item_ids)),
        "itemIds": item_ids,
        "lastUpdatedAt": _text_or_default(entry.get("lastUpdatedAt")),
        "lastSource": _text_or_default(entry.get("lastSource")),
    }


def _inventory_item_ids(entry: dict[str, Any]) -> list[str]:
    raw_item_ids = entry.get("itemIds") if isinstance(entry.get("itemIds"), list) else entry.get("item_ids")
    normalized: list[str] = []
    seen: set[str] = set()
    if isinstance(raw_item_ids, list):
        for raw_item_id in raw_item_ids:
            item_id = str(raw_item_id or "").strip()
            if not item_id or item_id in seen:
                continue
            normalized.append(item_id)
            seen.add(item_id)
    entry["itemIds"] = normalized
    entry["quantity"] = max(max(0, round(_numeric(entry.get("quantity")))), len(normalized))
    return normalized


def _inventory_take_item_ids(entry: dict[str, Any], take_qty: int) -> list[str]:
    item_ids = _inventory_item_ids(entry)
    safe_take_qty = max(0, min(len(item_ids), take_qty))
    taken = item_ids[:safe_take_qty]
    entry["itemIds"] = item_ids[safe_take_qty:]
    entry["quantity"] = max(0, round(_numeric(entry.get("quantity"))))
    return taken


def _work_order_requirement_key(raw: Any, fallback: str = "") -> str:
    entry = raw if isinstance(raw, dict) else {}
    return _text_or_default(
        entry.get("lineId")
        or entry.get("line_id")
        or entry.get("matchKey")
        or entry.get("match_key")
        or entry.get("color")
        or entry.get("productColor")
        or entry.get("product_code")
        or entry.get("productCode")
        or entry.get("stock_code")
        or entry.get("stockCode"),
        fallback,
    )


def _work_order_requirement_match_key(requirement: dict[str, Any]) -> str:
    return (
        str(requirement.get("matchKey") or "").strip()
        or str(requirement.get("color") or "").strip().lower()
        or str(requirement.get("productCode") or "").strip()
        or str(requirement.get("stockCode") or "").strip()
    )


def _work_order_requirement_label(requirement: dict[str, Any]) -> str:
    color = _normalize_order_color(
        requirement.get("color"),
        requirement.get("stockCode"),
        requirement.get("stockName"),
    )
    if color:
        return color
    return (
        str(requirement.get("stockCode") or "").strip()
        or str(requirement.get("productCode") or "").strip()
        or str(requirement.get("lineId") or "").strip()
        or "urun"
    )


def _sync_work_order_requirement(requirement: dict[str, Any]) -> None:
    quantity = max(0, round(_numeric(requirement.get("quantity"))))
    completed_qty = max(0, round(_numeric(requirement.get("completedQty"))))
    requirement["lineId"] = _text_or_default(
        requirement.get("lineId"),
        _work_order_requirement_match_key(requirement) or "line",
    )
    requirement["productCode"] = _text_or_default(
        requirement.get("productCode"),
        str(requirement.get("stockCode") or requirement.get("lineId") or ""),
    )
    requirement["stockCode"] = _text_or_default(
        requirement.get("stockCode"),
        str(requirement.get("productCode") or requirement.get("lineId") or ""),
    )
    requirement["stockName"] = _text_or_default(
        requirement.get("stockName"),
        str(requirement.get("stockCode") or requirement.get("productCode") or requirement.get("lineId") or ""),
    )
    requirement["color"] = _normalize_order_color(
        requirement.get("color"),
        requirement.get("stockCode"),
        requirement.get("stockName"),
    )
    requirement["matchKey"] = _text_or_default(
        requirement.get("matchKey"),
        requirement["color"] or requirement["productCode"] or requirement["stockCode"] or requirement["lineId"],
    )
    requirement["quantity"] = quantity
    requirement["completedQty"] = min(quantity, completed_qty)
    requirement["inventoryConsumedQty"] = min(
        requirement["completedQty"],
        max(0, round(_numeric(requirement.get("inventoryConsumedQty")))),
    )
    requirement["productionQty"] = min(
        quantity,
        max(0, round(_numeric(requirement.get("productionQty")))),
    )
    requirement["remainingQty"] = max(0, quantity - requirement["completedQty"])


def _normalize_work_order_requirement(
    raw: Any,
    *,
    existing: dict[str, Any] | None = None,
    fallback_line_id: str = "",
    fallback_product_code: str = "",
    fallback_stock_code: str = "",
    fallback_stock_name: str = "",
) -> dict[str, Any]:
    entry = raw if isinstance(raw, dict) else {}
    current = existing if isinstance(existing, dict) else {}
    color = _normalize_order_color(
        entry.get("color")
        or entry.get("product_color")
        or entry.get("productColor")
        or entry.get("renk"),
        entry.get("stock_code") or entry.get("stockCode") or entry.get("stok_kodu") or entry.get("lblMTM00_CODE"),
        entry.get("stock_name") or entry.get("stockName") or entry.get("stok_adi") or entry.get("lblMTM00_NAME"),
        current.get("color"),
        current.get("stockCode"),
        current.get("stockName"),
    )
    product_code = _text_or_default(
        entry.get("product_code")
        or entry.get("productCode")
        or entry.get("stock_code")
        or entry.get("stockCode")
        or entry.get("lblMTM00_CODE")
        or current.get("productCode"),
        fallback_product_code or fallback_stock_code or fallback_line_id,
    )
    stock_code = _text_or_default(
        entry.get("stock_code")
        or entry.get("stockCode")
        or entry.get("stok_kodu")
        or entry.get("lblMTM00_CODE")
        or current.get("stockCode"),
        fallback_stock_code or product_code or fallback_line_id,
    )
    stock_name = _text_or_default(
        entry.get("stock_name")
        or entry.get("stockName")
        or entry.get("stok_adi")
        or entry.get("stokAdÄ±")
        or entry.get("lblMTM00_NAME")
        or current.get("stockName"),
        fallback_stock_name or stock_code or product_code or fallback_line_id,
    )
    requirement = {
        "lineId": _text_or_default(
            entry.get("lineId")
            or entry.get("line_id")
            or current.get("lineId"),
            fallback_line_id or color or stock_code or product_code or "line",
        ),
        "productCode": product_code or stock_code or fallback_line_id,
        "stockCode": stock_code or product_code or fallback_line_id,
        "stockName": stock_name or stock_code or product_code or fallback_line_id,
        "color": color,
        "matchKey": _text_or_default(
            entry.get("matchKey") or entry.get("match_key") or current.get("matchKey"),
            color or product_code or stock_code or fallback_line_id,
        ),
        "quantity": max(0, round(_numeric(entry.get("qty") or entry.get("quantity") or entry.get("miktar") or entry.get("lblMMFB0_QTY") or current.get("quantity") or 0))),
        "completedQty": max(
            0,
            round(
                _numeric(
                    entry.get("completedQty")
                    or entry.get("completed_qty")
                    or current.get("completedQty")
                    or 0
                )
            ),
        ),
        "inventoryConsumedQty": max(
            0,
            round(
                _numeric(
                    entry.get("inventoryConsumedQty")
                    or entry.get("inventory_consumed_qty")
                    or current.get("inventoryConsumedQty")
                    or 0
                )
            ),
        ),
        "productionQty": max(
            0,
            round(
                _numeric(
                    entry.get("productionQty")
                    or entry.get("production_qty")
                    or current.get("productionQty")
                    or 0
                )
            ),
        ),
    }
    _sync_work_order_requirement(requirement)
    return requirement


def _normalize_work_order_requirements(entry: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    raw_requirements = entry.get("requirements") or entry.get("components") or entry.get("lines")
    current_requirements = current.get("requirements") if isinstance(current.get("requirements"), list) else []
    if isinstance(raw_requirements, list) and raw_requirements:
        source_rows = raw_requirements
    elif current_requirements:
        source_rows = current_requirements
    else:
        source_rows = [
            {
                "lineId": _text_or_default(entry.get("lineId") or current.get("lineId"), "line-1"),
                "productCode": entry.get("product_code") or entry.get("productCode") or entry.get("lblMTM00_CODE") or current.get("productCode"),
                "stockCode": entry.get("stock_code") or entry.get("stockCode") or entry.get("stok_kodu") or entry.get("lblMTM00_CODE") or current.get("stockCode"),
                "stockName": entry.get("stock_name") or entry.get("stockName") or entry.get("stok_adi") or entry.get("stokAdÄ±") or entry.get("lblMTM00_NAME") or current.get("stockName"),
                "color": entry.get("product_color") or entry.get("productColor") or entry.get("color") or current.get("productColor"),
                "matchKey": entry.get("matchKey") or current.get("matchKey"),
                "qty": entry.get("qty") or entry.get("quantity") or entry.get("miktar") or entry.get("lblMMFB0_QTY") or current.get("quantity"),
                "completedQty": entry.get("completedQty") or current.get("completedQty"),
                "inventoryConsumedQty": entry.get("inventoryConsumedQty") or current.get("inventoryConsumedQty"),
                "productionQty": entry.get("productionQty") or current.get("productionQty"),
            }
        ]

    current_lookup: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(current_requirements, start=1):
        if not isinstance(row, dict):
            continue
        current_lookup[_work_order_requirement_key(row, f"line-{index}")] = row

    fallback_product_code = _text_or_default(entry.get("product_code") or entry.get("productCode") or entry.get("lblMTM00_CODE") or current.get("productCode"))
    fallback_stock_code = _text_or_default(entry.get("stock_code") or entry.get("stockCode") or entry.get("stok_kodu") or entry.get("lblMTM00_CODE") or current.get("stockCode"))
    fallback_stock_name = _text_or_default(entry.get("stock_name") or entry.get("stockName") or entry.get("stok_adi") or entry.get("stokAdÄ±") or entry.get("lblMTM00_NAME") or current.get("stockName"))
    requirements: list[dict[str, Any]] = []
    for index, raw_row in enumerate(source_rows, start=1):
        if not isinstance(raw_row, dict):
            continue
        lookup_key = _work_order_requirement_key(raw_row, f"line-{index}")
        requirement = _normalize_work_order_requirement(
            raw_row,
            existing=current_lookup.get(lookup_key),
            fallback_line_id=lookup_key,
            fallback_product_code=fallback_product_code,
            fallback_stock_code=fallback_stock_code,
            fallback_stock_name=fallback_stock_name,
        )
        if (
            requirement["quantity"] > 0
            or requirement["completedQty"] > 0
            or requirement["inventoryConsumedQty"] > 0
            or requirement["productionQty"] > 0
        ):
            requirements.append(requirement)
    return requirements


def _normalize_work_order_row(raw: Any, *, existing: dict[str, Any] | None = None, queued_at: str = "") -> dict[str, Any]:
    entry = raw if isinstance(raw, dict) else {}
    current = existing if isinstance(existing, dict) else {}
    order_id = _text_or_default(
        entry.get("order_id")
        or entry.get("orderId")
        or entry.get("id")
        or entry.get("is_emri_no")
        or entry.get("iş_emri_no")
        or entry.get("system_no")
        or entry.get("systemNo")
        or entry.get("sistem_no")
        or entry.get("sistemNo")
        or entry.get("lblMMFB0_NUMBER")
        or current.get("orderId")
    )
    color = _normalize_order_color(
        entry.get("product_color")
        or entry.get("productColor")
        or entry.get("color")
        or entry.get("renk"),
        entry.get("stock_code") or entry.get("stockCode") or entry.get("stok_kodu") or entry.get("lblMTM00_CODE"),
        entry.get("stock_name") or entry.get("stockName") or entry.get("stok_adi") or entry.get("stokAdı") or entry.get("lblMTM00_NAME"),
        current.get("productColor"),
    )
    product_code = _text_or_default(
        entry.get("product_code")
        or entry.get("productCode")
        or entry.get("stock_code")
        or entry.get("stockCode")
        or entry.get("stok_kodu")
        or entry.get("stokKodu")
        or entry.get("lblMTM00_CODE")
        or current.get("productCode")
    )
    stock_code = _text_or_default(
        entry.get("stock_code")
        or entry.get("stockCode")
        or entry.get("stok_kodu")
        or entry.get("stokKodu")
        or entry.get("lblMTM00_CODE")
        or current.get("stockCode")
        or product_code
    )
    stock_name = _text_or_default(
        entry.get("stock_name")
        or entry.get("stockName")
        or entry.get("stok_adi")
        or entry.get("stokAdı")
        or entry.get("lblMTM00_NAME")
        or current.get("stockName"),
        stock_code or order_id,
    )
    status = _text_or_default(entry.get("status"), str(current.get("status") or "queued")).lower()
    if status not in WORK_ORDER_STATUSES:
        status = "queued"
    requirements = _normalize_work_order_requirements(entry, current)
    setup_time_ms = _duration_ms(
        _first_present(
            entry.get("setup_time_ms"),
            entry.get("setupTimeMs"),
            current.get("setupTimeMs"),
        ),
        default=_duration_ms(
            _first_present(
                entry.get("setup_time_sec"),
                entry.get("setupTimeSec"),
                entry.get("hazirlik_suresi_sec"),
                entry.get("hazÄ±rlÄ±k_sÃ¼resi_sn"),
                entry.get("lblMMFB4_SETUP_TIME"),
                current.get("setupTimeSec"),
            ),
            multiplier=1000.0,
        ),
    )
    cycle_time_ms = _duration_ms(
        _first_present(
            entry.get("cycle_time_ms"),
            entry.get("cycleTimeMs"),
            current.get("cycleTimeMs"),
        ),
        default=_duration_ms(
            _first_present(
                entry.get("cycle_time_sec"),
                entry.get("cycleTimeSec"),
                entry.get("sure_sec"),
                entry.get("sÃ¼re_saniye"),
                entry.get("lblMMFB4_TIME"),
                current.get("cycleTimeSec"),
            ),
            multiplier=1000.0,
        ),
    )
    order = {
        "orderId": order_id,
        "erpType": _text_or_default(entry.get("erp_type") or entry.get("erpType") or entry.get("tip") or current.get("erpType"), "Is Emirleri"),
        "date": _text_or_default(entry.get("date") or entry.get("tarih") or entry.get("lblMMFB0_DATE") or current.get("date")),
        "systemNo": _text_or_default(entry.get("system_no") or entry.get("systemNo") or entry.get("sistem_no") or entry.get("sistemNo") or entry.get("lblMMFB0_NUMBER") or current.get("systemNo")),
        "sequenceNo": max(0, round(_numeric(entry.get("sequence_no") or entry.get("sequenceNo") or entry.get("sira") or entry.get("sıra") or entry.get("lblMMFB0_PRNT_ORDER") or current.get("sequenceNo")))),
        "locked": _boolish(entry.get("locked") if entry.get("locked") is not None else entry.get("kilit") if entry.get("kilit") is not None else entry.get("lblPRNT_ORDER_UPD") if entry.get("lblPRNT_ORDER_UPD") is not None else current.get("locked")),
        "stockType": _text_or_default(entry.get("stock_type") or entry.get("stockType") or entry.get("stok_servis") or entry.get("stokServis") or entry.get("lblMTMT0_CODE") or current.get("stockType")),
        "stockCode": stock_code,
        "stockName": stock_name,
        "unit": _text_or_default(entry.get("unit") or entry.get("birim") or entry.get("lblMUNT0_CODE") or current.get("unit")),
        "methodCode": _text_or_default(entry.get("method_code") or entry.get("methodCode") or entry.get("metod_kodu") or entry.get("metodKodu") or entry.get("lblMTMM0_CODE") or current.get("methodCode")),
        "lotCode": _text_or_default(entry.get("lot_code") or entry.get("lotCode") or entry.get("lot_kodu") or entry.get("lblMTML0_CODE") or current.get("lotCode")),
        "cutCode": _text_or_default(entry.get("cut_code") or entry.get("cutCode") or entry.get("kesim_kodu") or entry.get("lblFPJ09_CODE") or current.get("cutCode")),
        "partyNo": _text_or_default(entry.get("party_no") or entry.get("partyNo") or entry.get("parti_no") or entry.get("lblMTML0_PRTY_NO") or current.get("partyNo")),
        "quantity": 0,
        "projectCode": _text_or_default(entry.get("project_code") or entry.get("projectCode") or entry.get("proje") or entry.get("lblFPJ00_ID") or current.get("projectCode")),
        "description": _text_or_default(entry.get("description") or entry.get("aciklama") or entry.get("açıklama") or entry.get("lblMMFB0_DESC") or current.get("description")),
        "workCenterCode": _text_or_default(entry.get("work_center_code") or entry.get("workCenterCode") or entry.get("is_merkezi") or entry.get("iş_merkezi") or entry.get("lblMFW00_CODE") or current.get("workCenterCode")),
        "workStationCode": _text_or_default(entry.get("work_station_code") or entry.get("workStationCode") or entry.get("is_istasyonu") or entry.get("iş_istasyonu") or entry.get("lblMFW01_CODE") or current.get("workStationCode")),
        "operationCode": _text_or_default(entry.get("operation_code") or entry.get("operationCode") or entry.get("operasyon") or entry.get("lblMFWO0_CODE") or current.get("operationCode")),
        "setupTimeSec": max(0.0, _numeric(entry.get("setup_time_sec") or entry.get("setupTimeSec") or entry.get("hazirlik_suresi_sec") or entry.get("hazırlık_süresi_sn") or entry.get("lblMMFB4_SETUP_TIME") or current.get("setupTimeSec"))),
        "workerCount": max(0, round(_numeric(entry.get("worker_count") or entry.get("workerCount") or entry.get("isci_sayisi") or entry.get("işçi_sayısı") or entry.get("lblMMFB4_WORKER_COUNT") or current.get("workerCount")))),
        "cycleTimeSec": max(0.0, _numeric(entry.get("cycle_time_sec") or entry.get("cycleTimeSec") or entry.get("sure_sec") or entry.get("süre_saniye") or entry.get("lblMMFB4_TIME") or current.get("cycleTimeSec"))),
        "setupTimeMs": setup_time_ms,
        "setupTimeSec": _seconds_from_ms(setup_time_ms),
        "cycleTimeMs": cycle_time_ms,
        "cycleTimeSec": _seconds_from_ms(cycle_time_ms),
        "shiftCode": _text_or_default(entry.get("shift_code") or entry.get("shiftCode") or entry.get("vardiya") or entry.get("lblMMFB4_SHIFT_TYPE") or current.get("shiftCode")),
        "productCode": product_code or stock_code or order_id,
        "productColor": color,
        "matchKey": _text_or_default(entry.get("matchKey") or current.get("matchKey"), color or product_code or stock_code or order_id),
        "status": status,
        "queuedAt": _text_or_default(entry.get("queuedAt") or current.get("queuedAt"), queued_at),
        "startedAt": _text_or_default(entry.get("startedAt") or current.get("startedAt")),
        "autoCompletedAt": _text_or_default(entry.get("autoCompletedAt") or current.get("autoCompletedAt")),
        "completedAt": _text_or_default(entry.get("completedAt") or current.get("completedAt")),
        "startedBy": _text_or_default(entry.get("startedBy") or entry.get("lblFCR00_ACC_CODE_PR") or current.get("startedBy")),
        "startedByName": _text_or_default(entry.get("startedByName") or entry.get("lblFCR00_NAME_PR") or current.get("startedByName")),
        "transitionReason": _text_or_default(entry.get("transitionReason") or current.get("transitionReason")),
        "inventoryConsumedQty": 0,
        "productionQty": 0,
        "completedQty": 0,
        "remainingQty": 0,
        "lastAllocationAt": _text_or_default(entry.get("lastAllocationAt") or current.get("lastAllocationAt")),
        "requirements": requirements,
    }
    _sync_work_order_row(order)
    return order


def _completed_item_match_key(item: dict[str, Any], item_key: str = "") -> str:
    return _normalize_order_color(
        item.get("final_color"),
        item.get("color"),
        item.get("sensor_color"),
        item.get("product_code"),
        item.get("stock_code"),
        item.get("stock_name"),
    )


def _inventory_backfill_disabled(item: dict[str, Any]) -> bool:
    return bool(item.get("inventory_backfill_disabled"))


def _backfill_completed_item_inventory(state: dict[str, Any]) -> None:
    items = state.get("itemsById") if isinstance(state.get("itemsById"), dict) else {}
    work_orders = state.get("workOrders") if isinstance(state.get("workOrders"), dict) else default_work_order_state()
    inventory = work_orders.get("inventoryByProduct") if isinstance(work_orders.get("inventoryByProduct"), dict) else {}
    work_orders["inventoryByProduct"] = inventory
    state["workOrders"] = work_orders

    for item_key, item in items.items():
        if not isinstance(item, dict) or not item.get("completed_at"):
            continue
        if str(item.get("work_order_id") or "").strip():
            continue
        if _normalize_classification(item.get("classification")) == "SCRAP":
            continue
        if _inventory_backfill_disabled(item):
            continue

        item_id = str(item.get("item_id") or item_key).strip()
        if not item_id:
            continue

        match_key = str(item.get("inventory_match_key") or "").strip() or _completed_item_match_key(item, item_key)
        if not match_key:
            continue

        color = _normalize_order_color(item.get("final_color"), item.get("color"), item.get("sensor_color"), match_key)
        product_code = str(item.get("product_code") or item.get("stock_code") or "").strip() or match_key.upper()
        stock_code = str(item.get("stock_code") or item.get("product_code") or "").strip() or product_code or match_key.upper()
        stock_name = str(item.get("stock_name") or "").strip() or (color or match_key).upper()
        entry = _ensure_inventory_entry(
            inventory,
            match_key,
            product_code=product_code,
            stock_code=stock_code,
            stock_name=stock_name,
            color=color,
        )
        item_ids = _inventory_item_ids(entry)
        if item_id not in item_ids:
            item_ids.append(item_id)
            entry["itemIds"] = item_ids
        entry["quantity"] = max(max(0, round(_numeric(entry.get("quantity")))), len(item_ids))
        entry["lastUpdatedAt"] = str(item.get("updated_at") or item.get("completed_at") or entry.get("lastUpdatedAt") or "")
        entry["lastSource"] = str(entry.get("lastSource") or item.get("inventoryAction") or "legacy_inventory_backfill")

        item["inventory_match_key"] = match_key
        if not str(item.get("inventoryAction") or "").strip():
            item["inventoryAction"] = "legacy_inventory_backfill"
        item["inventory_backfill_disabled"] = False
        item["work_order_match_key"] = str(item.get("work_order_match_key") or "")
        item["work_order_id"] = str(item.get("work_order_id") or "")


def _detach_inventory_item_reference(state: dict[str, Any], item_key: str) -> None:
    if not item_key:
        return
    inventory = _work_order_inventory(state)
    for entry in inventory.values():
        if not isinstance(entry, dict):
            continue
        item_ids = _inventory_item_ids(entry)
        if item_key not in item_ids:
            continue
        next_ids = [value for value in item_ids if value != item_key]
        entry["itemIds"] = next_ids
        entry["quantity"] = max(max(0, round(_numeric(entry.get("quantity")))), len(next_ids))


def _has_new_cycle_after_completion(item: dict[str, Any]) -> bool:
    completed_at = _parse_iso(str(item.get("completed_at") or ""))
    if completed_at is None:
        return False
    for field in ("queued_at", "measured_at", "detected_at", "picked_at"):
        observed_at = _parse_iso(str(item.get(field) or ""))
        if observed_at is not None and observed_at > completed_at:
            return True
    return False


def _sanitize_reused_items_after_load(state: dict[str, Any]) -> None:
    items = state.get("itemsById") if isinstance(state.get("itemsById"), dict) else {}
    recent_ids = state.get("recentItemIds") if isinstance(state.get("recentItemIds"), list) else []
    sanitized_recent = [value for value in recent_ids if value in items]
    changed_recent = len(sanitized_recent) != len(recent_ids)

    for item_key, item in items.items():
        if not isinstance(item, dict) or not _has_new_cycle_after_completion(item):
            continue
        _detach_inventory_item_reference(state, item_key)
        sanitized_recent = [value for value in sanitized_recent if value != item_key]
        for field in (
            "completed_at",
            "released_at",
            "return_started_at",
            "return_reached_at",
            "return_done_at",
            "final_color_frozen_at",
            "override_applied_at",
            "override_source",
            "work_order_id",
            "work_order_match_key",
            "inventory_match_key",
            "inventoryAction",
        ):
            item[field] = ""
        item["queue_status"] = str(item.get("queue_status") or "waiting_travel")
    if changed_recent or len(sanitized_recent) != len(recent_ids):
        state["recentItemIds"] = sanitized_recent[:10]


def ensure_runtime_state_shape(payload: Any) -> dict[str, Any]:
    candidate = payload if isinstance(payload, dict) else {}
    base = default_runtime_state()

    selected = str(candidate.get("shiftSelected") or base["shiftSelected"]).upper()
    base["shiftSelected"] = selected if selected in SHIFT_PRESETS else base["shiftSelected"]

    performance_mode = str(candidate.get("performanceMode") or base["performanceMode"]).upper()
    base["performanceMode"] = "IDEAL_CYCLE" if performance_mode == "IDEAL_CYCLE" else "TARGET"
    base["version"] = int(candidate.get("version") or base["version"])
    base["targetQty"] = max(0, round(_numeric(_first_present(candidate.get("targetQty"), base["targetQty"]))))
    base["idealCycleMs"] = _duration_ms(
        _first_present(candidate.get("idealCycleMs"), candidate.get("idealCycleSec")),
        multiplier=1000.0 if candidate.get("idealCycleMs") in (None, "") else 1.0,
        default=base["idealCycleMs"],
    )
    base["idealCycleSec"] = _seconds_from_ms(base["idealCycleMs"])
    base["plannedStopMs"] = _duration_ms(
        _first_present(candidate.get("plannedStopMs"), candidate.get("plannedStopMin")),
        multiplier=60_000.0 if candidate.get("plannedStopMs") in (None, "") else 1.0,
        default=base["plannedStopMs"],
    )
    base["plannedStopMin"] = _minutes_from_ms(base["plannedStopMs"])

    shift = candidate.get("shift") if isinstance(candidate.get("shift"), dict) else {}
    base["shift"].update(shift)
    base["shift"]["active"] = bool(base["shift"].get("active"))
    base["shift"]["code"] = str(base["shift"].get("code") or "")
    base["shift"]["name"] = str(base["shift"].get("name") or "")
    base["shift"]["startedAt"] = str(base["shift"].get("startedAt") or "")
    base["shift"]["endedAt"] = str(base["shift"].get("endedAt") or "")
    base["shift"]["planStart"] = str(base["shift"].get("planStart") or "")
    base["shift"]["planEnd"] = str(base["shift"].get("planEnd") or "")
    shift_mode = str(base["shift"].get("performanceMode") or base["performanceMode"]).upper()
    base["shift"]["performanceMode"] = "IDEAL_CYCLE" if shift_mode == "IDEAL_CYCLE" else "TARGET"
    base["shift"]["targetQty"] = max(0, round(_numeric(_first_present(base["shift"].get("targetQty"), base["targetQty"]))))
    base["shift"]["idealCycleMs"] = _duration_ms(
        _first_present(base["shift"].get("idealCycleMs"), base["shift"].get("idealCycleSec")),
        multiplier=1000.0 if base["shift"].get("idealCycleMs") in (None, "") else 1.0,
        default=base["idealCycleMs"],
    )
    base["shift"]["idealCycleSec"] = _seconds_from_ms(base["shift"]["idealCycleMs"])
    base["shift"]["plannedStopMs"] = _duration_ms(
        _first_present(base["shift"].get("plannedStopMs"), base["shift"].get("plannedStopMin")),
        multiplier=60_000.0 if base["shift"].get("plannedStopMs") in (None, "") else 1.0,
        default=base["plannedStopMs"],
    )
    base["shift"]["plannedStopMin"] = _minutes_from_ms(base["shift"]["plannedStopMs"])

    counts = candidate.get("counts") if isinstance(candidate.get("counts"), dict) else {}
    base["counts"].update(counts)
    by_color = counts.get("byColor") if isinstance(counts.get("byColor"), dict) else {}
    base["counts"]["total"] = max(0, round(_numeric(base["counts"].get("total"))))
    base["counts"]["good"] = max(0, round(_numeric(base["counts"].get("good"))))
    base["counts"]["rework"] = max(0, round(_numeric(base["counts"].get("rework"))))
    base["counts"]["scrap"] = max(0, round(_numeric(base["counts"].get("scrap"))))
    base["counts"]["byColor"] = {
        color: {
            "total": max(0, round(_numeric((by_color.get(color) or {}).get("total")))),
            "good": max(0, round(_numeric((by_color.get(color) or {}).get("good")))),
            "rework": max(0, round(_numeric((by_color.get(color) or {}).get("rework")))),
            "scrap": max(0, round(_numeric((by_color.get(color) or {}).get("scrap")))),
        }
        for color in ("red", "yellow", "blue")
    }

    base["itemsById"] = candidate.get("itemsById") if isinstance(candidate.get("itemsById"), dict) else {}
    base["queueOrder"] = candidate.get("queueOrder") if isinstance(candidate.get("queueOrder"), list) else []
    base["recentItemIds"] = candidate.get("recentItemIds") if isinstance(candidate.get("recentItemIds"), list) else []
    work_orders = candidate.get("workOrders") if isinstance(candidate.get("workOrders"), dict) else {}
    base["workOrders"]["toleranceMs"] = _duration_ms(
        _first_present(work_orders.get("toleranceMs"), work_orders.get("toleranceMinutes")),
        multiplier=60_000.0 if work_orders.get("toleranceMs") in (None, "") else 1.0,
        default=base["workOrders"]["toleranceMs"],
    )
    base["workOrders"]["toleranceMinutes"] = _minutes_from_ms(base["workOrders"]["toleranceMs"])
    raw_orders = work_orders.get("ordersById") if isinstance(work_orders.get("ordersById"), dict) else {}
    normalized_orders: dict[str, dict[str, Any]] = {}
    for raw_key, raw_order in raw_orders.items():
        normalized = _normalize_work_order_row(raw_order, queued_at="")
        order_id = normalized["orderId"] or str(raw_key or "").strip()
        if not order_id:
            continue
        normalized["orderId"] = order_id
        if not normalized["queuedAt"]:
            normalized["queuedAt"] = str(work_orders.get("importedAt") or "")
        normalized["completedQty"] = min(normalized["quantity"], normalized["completedQty"])
        normalized["inventoryConsumedQty"] = min(normalized["completedQty"], normalized["inventoryConsumedQty"])
        normalized["productionQty"] = min(normalized["quantity"], normalized["productionQty"])
        normalized["remainingQty"] = max(0, normalized["quantity"] - normalized["completedQty"])
        if normalized["status"] == "pending_approval" and normalized["remainingQty"] > 0:
            normalized["status"] = "active"
            normalized["autoCompletedAt"] = ""
        if normalized["status"] == "completed" and not normalized["completedAt"]:
            normalized["completedAt"] = normalized["lastAllocationAt"] or normalized["startedAt"]
        if normalized["status"] in {"pending_approval", "completed"} and not normalized["autoCompletedAt"]:
            normalized["autoCompletedAt"] = normalized["lastAllocationAt"] or normalized["completedAt"] or normalized["startedAt"]
        if normalized["status"] == "active" and not normalized["startedAt"]:
            normalized["status"] = "queued"
        if normalized["status"] == "queued":
            normalized["autoCompletedAt"] = ""
            normalized["completedAt"] = ""
        normalized_orders[order_id] = normalized
    base["workOrders"]["ordersById"] = normalized_orders
    raw_sequence = work_orders.get("orderSequence") if isinstance(work_orders.get("orderSequence"), list) else []
    sequence: list[str] = []
    for item in raw_sequence:
        order_id = str(item or "").strip()
        if order_id and order_id in normalized_orders and order_id not in sequence:
            sequence.append(order_id)
    for order_id in normalized_orders:
        if order_id not in sequence:
            sequence.append(order_id)
    base["workOrders"]["orderSequence"] = sequence
    active_order_id = str(work_orders.get("activeOrderId") or "").strip()
    if active_order_id not in normalized_orders or normalized_orders.get(active_order_id, {}).get("status") not in WORK_ORDER_BLOCKING_STATUSES:
        active_order_id = ""
        for order_id in sequence:
            if normalized_orders.get(order_id, {}).get("status") in WORK_ORDER_BLOCKING_STATUSES:
                active_order_id = order_id
                break
    base["workOrders"]["activeOrderId"] = active_order_id
    base["workOrders"]["lastCompletedOrderId"] = str(work_orders.get("lastCompletedOrderId") or "").strip()
    base["workOrders"]["lastCompletedAt"] = str(work_orders.get("lastCompletedAt") or "")
    inventory = work_orders.get("inventoryByProduct") if isinstance(work_orders.get("inventoryByProduct"), dict) else {}
    base["workOrders"]["inventoryByProduct"] = {
        key: _normalize_inventory_row(value, str(key or "").strip())
        for key, value in inventory.items()
        if str(key or "").strip()
    }
    _sanitize_reused_items_after_load(base)
    _backfill_completed_item_inventory(base)
    base["workOrders"]["transitionLog"] = work_orders.get("transitionLog") if isinstance(work_orders.get("transitionLog"), list) else []
    base["workOrders"]["completionLog"] = work_orders.get("completionLog") if isinstance(work_orders.get("completionLog"), list) else []
    source = work_orders.get("source") if isinstance(work_orders.get("source"), dict) else {}
    base["workOrders"]["source"] = {
        "folder": str(source.get("folder") or ""),
        "file": str(source.get("file") or ""),
        "loadedAt": str(source.get("loadedAt") or ""),
    }
    base["processedVisionEventKeys"] = candidate.get("processedVisionEventKeys") if isinstance(candidate.get("processedVisionEventKeys"), list) else []
    base["activeFault"] = _normalize_fault_row(candidate.get("activeFault")) if isinstance(candidate.get("activeFault"), dict) else None
    base["faultHistory"] = [
        _normalize_fault_row(row)
        for row in (candidate.get("faultHistory") if isinstance(candidate.get("faultHistory"), list) else [])
        if isinstance(row, dict)
    ]
    base["unplannedDowntimeMs"] = max(0, round(_numeric(candidate.get("unplannedDowntimeMs"))))
    base["manualFaultDurationMs"] = max(0, round(_numeric(candidate.get("manualFaultDurationMs"))))
    base["trend"] = candidate.get("trend") if isinstance(candidate.get("trend"), list) else []
    base["qualityOverrideLog"] = candidate.get("qualityOverrideLog") if isinstance(candidate.get("qualityOverrideLog"), list) else []
    base["qualityOverrideResetAt"] = str(candidate.get("qualityOverrideResetAt") or "")
    base["earlyPickRejectLog"] = candidate.get("earlyPickRejectLog") if isinstance(candidate.get("earlyPickRejectLog"), list) else []
    base["maintenance"] = candidate.get("maintenance") if isinstance(candidate.get("maintenance"), dict) else default_maintenance_state()
    base["helpRequest"] = candidate.get("helpRequest") if isinstance(candidate.get("helpRequest"), dict) else default_help_request_state()
    base["deviceRegistry"] = candidate.get("deviceRegistry") if isinstance(candidate.get("deviceRegistry"), dict) else {}
    base["deviceSessions"] = candidate.get("deviceSessions") if isinstance(candidate.get("deviceSessions"), dict) else {}
    vision = candidate.get("vision") if isinstance(candidate.get("vision"), dict) else {}
    base["vision"]["healthState"] = str(vision.get("healthState") or "offline")
    base["vision"]["badWindows"] = max(0, round(_numeric(vision.get("badWindows"))))
    base["vision"]["goodWindows"] = max(0, round(_numeric(vision.get("goodWindows"))))
    base["vision"]["fps"] = max(0.0, _numeric(vision.get("fps")))
    base["vision"]["eventLatencyMs"] = None if vision.get("eventLatencyMs") in (None, "") else max(0.0, _numeric(vision.get("eventLatencyMs")))
    base["vision"]["lastStatusAt"] = str(vision.get("lastStatusAt") or "")
    base["vision"]["lastTracksAt"] = str(vision.get("lastTracksAt") or "")
    base["vision"]["lastHeartbeatAt"] = str(vision.get("lastHeartbeatAt") or "")
    base["vision"]["lastEventAt"] = str(vision.get("lastEventAt") or "")
    base["vision"]["lastObservedAt"] = str(vision.get("lastObservedAt") or "")
    base["vision"]["lastPublishedAt"] = str(vision.get("lastPublishedAt") or "")
    base["vision"]["lastReceivedAt"] = str(vision.get("lastReceivedAt") or "")
    base["vision"]["lastRejectReason"] = str(vision.get("lastRejectReason") or "")
    metrics = vision.get("metrics") if isinstance(vision.get("metrics"), dict) else {}
    base["vision"]["metrics"] = {
        "mismatchCount": max(0, round(_numeric(metrics.get("mismatchCount")))),
        "earlyAcceptedCount": max(0, round(_numeric(metrics.get("earlyAcceptedCount")))),
        "earlyRejectedCount": max(0, round(_numeric(metrics.get("earlyRejectedCount")))),
        "lateAuditCount": max(0, round(_numeric(metrics.get("lateAuditCount")))),
    }
    base["lastSnapshotLoggedAt"] = str(candidate.get("lastSnapshotLoggedAt") or "")
    base["lastEventSummary"] = str(candidate.get("lastEventSummary") or base["lastEventSummary"])
    base["lastTabletLine"] = str(candidate.get("lastTabletLine") or "")
    base["lastUpdatedAt"] = str(candidate.get("lastUpdatedAt") or "")
    _maintenance_state(base)
    _help_request_state(base)
    _device_registry_state(base)
    _device_sessions_state(base)
    _refresh_operational_state(base)
    return base


def _set_summary(state: dict[str, Any], text: str, *, now: datetime) -> None:
    state["lastEventSummary"] = text
    state["lastUpdatedAt"] = _pseudo_iso_text(now)


def _close_active_fault(state: dict[str, Any], *, ended_at: str) -> None:
    active_fault = state.get("activeFault")
    if not isinstance(active_fault, dict):
        return
    started_at = str(active_fault.get("startedAt") or ended_at)
    duration_ms = max(0, round(_numeric(active_fault.get("durationMs"))))
    try:
        start_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
        if end_dt >= start_dt:
            duration_ms = int((end_dt - start_dt).total_seconds() * 1000)
    except ValueError:
        duration_ms = max(0, round(_numeric(active_fault.get("durationMin")) * 60000))
    if bool(active_fault.get("countsTowardUnplanned", True)):
        state["unplannedDowntimeMs"] = max(0, round(_numeric(state.get("unplannedDowntimeMs")))) + duration_ms
    if str(active_fault.get("source") or "").strip().lower() == "kiosk":
        state["manualFaultDurationMs"] = max(0, round(_numeric(state.get("manualFaultDurationMs")))) + duration_ms
    history = state["faultHistory"] if isinstance(state.get("faultHistory"), list) else []
    history.insert(
        0,
        {
            "faultId": str(active_fault.get("faultId") or ""),
            "category": str(active_fault.get("category") or "BILINMIYOR"),
            "reasonCode": str(active_fault.get("reasonCode") or ""),
            "reason": str(active_fault.get("reason") or "Bilinmiyor"),
            "startedAt": started_at,
            "endedAt": ended_at,
            "durationMs": duration_ms,
            "durationMin": _minutes_from_ms(duration_ms, precision=3),
            "source": str(active_fault.get("source") or ""),
            "deviceId": str(active_fault.get("deviceId") or ""),
            "deviceName": str(active_fault.get("deviceName") or ""),
            "operatorId": str(active_fault.get("operatorId") or ""),
            "operatorCode": str(active_fault.get("operatorCode") or ""),
            "operatorName": str(active_fault.get("operatorName") or ""),
            "boundStationId": str(active_fault.get("boundStationId") or ""),
            "countsTowardUnplanned": bool(active_fault.get("countsTowardUnplanned", True)),
        },
    )
    state["faultHistory"] = history[:20]
    state["activeFault"] = None
    _refresh_operational_state(state)


def _summary_counts(state: dict[str, Any]) -> dict[str, int]:
    counts = state.get("counts") if isinstance(state.get("counts"), dict) else {}
    return {
        "total": max(0, round(_numeric(counts.get("total")))),
        "good": max(0, round(_numeric(counts.get("good")))),
        "rework": max(0, round(_numeric(counts.get("rework")))),
        "scrap": max(0, round(_numeric(counts.get("scrap")))),
    }


def _normalize_classification(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"GOOD", "REWORK", "SCRAP"}:
        return text
    return "GOOD"


def _classification_bucket_name(value: str) -> str:
    return _normalize_classification(value).lower()


def _prepend_capped(rows: list[dict[str, Any]], row: dict[str, Any], *, limit: int = 20) -> list[dict[str, Any]]:
    rows.insert(0, row)
    return rows[:limit]


def _work_orders_state(state: dict[str, Any]) -> dict[str, Any]:
    work_orders = state.get("workOrders")
    if not isinstance(work_orders, dict):
        work_orders = default_work_order_state()
        state["workOrders"] = work_orders
    if not isinstance(work_orders.get("ordersById"), dict):
        work_orders["ordersById"] = {}
    if not isinstance(work_orders.get("orderSequence"), list):
        work_orders["orderSequence"] = []
    if not isinstance(work_orders.get("inventoryByProduct"), dict):
        work_orders["inventoryByProduct"] = {}
    if not isinstance(work_orders.get("transitionLog"), list):
        work_orders["transitionLog"] = []
    if not isinstance(work_orders.get("completionLog"), list):
        work_orders["completionLog"] = []
    if not isinstance(work_orders.get("source"), dict):
        work_orders["source"] = default_work_order_state()["source"]
    work_orders["toleranceMs"] = _duration_ms(
        _first_present(work_orders.get("toleranceMs"), work_orders.get("toleranceMinutes")),
        multiplier=60_000.0 if work_orders.get("toleranceMs") in (None, "") else 1.0,
    )
    work_orders["toleranceMinutes"] = _minutes_from_ms(work_orders["toleranceMs"])
    work_orders["activeOrderId"] = str(work_orders.get("activeOrderId") or "").strip()
    work_orders["lastCompletedOrderId"] = str(work_orders.get("lastCompletedOrderId") or "").strip()
    work_orders["lastCompletedAt"] = str(work_orders.get("lastCompletedAt") or "")
    return work_orders


def _work_order_orders(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return _work_orders_state(state)["ordersById"]


def _work_order_sequence(state: dict[str, Any]) -> list[str]:
    return _work_orders_state(state)["orderSequence"]


def _work_order_inventory(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return _work_orders_state(state)["inventoryByProduct"]


def _work_order_requirements(order: dict[str, Any]) -> list[dict[str, Any]]:
    requirements = order.get("requirements")
    if not isinstance(requirements, list):
        requirements = []
        order["requirements"] = requirements
    normalized: list[dict[str, Any]] = []
    for row in requirements:
        if not isinstance(row, dict):
            continue
        _sync_work_order_requirement(row)
        normalized.append(row)
    order["requirements"] = normalized
    return normalized


def _find_matching_requirement(order: dict[str, Any], match_key: str) -> dict[str, Any] | None:
    normalized_match = str(match_key or "").strip().lower()
    if not normalized_match:
        return None
    for requirement in _work_order_requirements(order):
        if max(0, round(_numeric(requirement.get("remainingQty")))) <= 0:
            continue
        if _work_order_requirement_match_key(requirement).lower() == normalized_match:
            return requirement
    return None


def _work_order_log_row(order: dict[str, Any], *, event_type: str, stamp: str, note: str = "") -> dict[str, Any]:
    return {
        "eventType": event_type,
        "time": stamp,
        "orderId": str(order.get("orderId") or ""),
        "stockCode": str(order.get("stockCode") or ""),
        "stockName": str(order.get("stockName") or ""),
        "quantity": max(0, round(_numeric(order.get("quantity")))),
        "completedQty": max(0, round(_numeric(order.get("completedQty")))),
        "remainingQty": max(0, round(_numeric(order.get("remainingQty")))),
        "startedBy": str(order.get("startedBy") or ""),
        "startedByName": str(order.get("startedByName") or ""),
        "note": note,
    }


def _sync_work_order_row(order: dict[str, Any]) -> None:
    requirements = _work_order_requirements(order)
    if requirements:
        order["quantity"] = sum(max(0, round(_numeric(requirement.get("quantity")))) for requirement in requirements)
        order["completedQty"] = sum(max(0, round(_numeric(requirement.get("completedQty")))) for requirement in requirements)
        order["inventoryConsumedQty"] = sum(max(0, round(_numeric(requirement.get("inventoryConsumedQty")))) for requirement in requirements)
        order["productionQty"] = sum(max(0, round(_numeric(requirement.get("productionQty")))) for requirement in requirements)
        order["remainingQty"] = sum(max(0, round(_numeric(requirement.get("remainingQty")))) for requirement in requirements)
        if len(requirements) == 1:
            requirement = requirements[0]
            order["productColor"] = _normalize_order_color(order.get("productColor"), requirement.get("color"), requirement.get("stockCode"), requirement.get("stockName"))
            order["matchKey"] = _text_or_default(order.get("matchKey"), _work_order_requirement_match_key(requirement))
        else:
            order["productColor"] = "mixed"
            order["matchKey"] = "mixed"
        return
    quantity = max(0, round(_numeric(order.get("quantity"))))
    completed_qty = max(0, round(_numeric(order.get("completedQty"))))
    order["quantity"] = quantity
    order["completedQty"] = min(quantity, completed_qty)
    order["inventoryConsumedQty"] = min(order["completedQty"], max(0, round(_numeric(order.get("inventoryConsumedQty")))))
    order["productionQty"] = min(quantity, max(0, round(_numeric(order.get("productionQty")))))
    order["remainingQty"] = max(0, quantity - order["completedQty"])


def _persist_work_order_metrics(state: dict[str, Any], order: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    snapshot = build_work_order_snapshot(state, order, now=now)
    order["goodQty"] = snapshot["goodQty"]
    order["reworkQty"] = snapshot["reworkQty"]
    order["scrapQty"] = snapshot["scrapQty"]
    order["plannedDurationMs"] = snapshot["plannedDurationMs"]
    order["runtimeMs"] = snapshot["runtimeMs"]
    order["unplannedMs"] = snapshot["unplannedMs"]
    order["availability"] = None
    order["performance"] = round(snapshot["performance"] * 100.0, 1)
    order["quality"] = round(snapshot["quality"] * 100.0, 1)
    order["oee"] = None
    return snapshot


def _ensure_inventory_entry(
    inventory: dict[str, dict[str, Any]],
    match_key: str,
    *,
    product_code: str = "",
    stock_code: str = "",
    stock_name: str = "",
    color: str = "",
) -> dict[str, Any]:
    entry = inventory.get(match_key)
    if not isinstance(entry, dict):
        entry = _normalize_inventory_row(
            {
                "matchKey": match_key,
                "productCode": product_code or stock_code or match_key,
                "stockCode": stock_code or product_code or match_key,
                "stockName": stock_name or product_code or stock_code or color or match_key,
                "color": color,
                "quantity": 0,
            },
            match_key,
        )
        inventory[match_key] = entry
    _inventory_item_ids(entry)
    return entry


def _assign_item_to_work_order(
    item: dict[str, Any],
    order: dict[str, Any],
    requirement: dict[str, Any],
    *,
    action: str,
) -> str:
    match_key = _work_order_requirement_match_key(requirement)
    item["work_order_id"] = str(order.get("orderId") or "")
    item["work_order_match_key"] = match_key
    item["inventoryAction"] = action
    item["inventory_match_key"] = match_key if action == "consumed_for_work_order" else ""
    item["inventory_backfill_disabled"] = False
    return match_key


def _push_inventory_quantity(
    inventory: dict[str, dict[str, Any]],
    match_key: str,
    *,
    quantity: int,
    received_at: str,
    source: str,
    product_code: str = "",
    stock_code: str = "",
    stock_name: str = "",
    color: str = "",
) -> dict[str, Any]:
    entry = _ensure_inventory_entry(
        inventory,
        match_key,
        product_code=product_code,
        stock_code=stock_code,
        stock_name=stock_name,
        color=color,
    )
    entry["quantity"] = max(0, round(_numeric(entry.get("quantity")))) + max(0, quantity)
    entry["lastUpdatedAt"] = received_at
    entry["lastSource"] = source
    return entry


def _move_completed_item_to_inventory(
    state: dict[str, Any],
    item: dict[str, Any],
    *,
    match_key: str,
    received_at: str,
    source: str,
    product_code: str = "",
    stock_code: str = "",
    stock_name: str = "",
    color: str = "",
) -> None:
    item_id = str(item.get("item_id") or "").strip()
    inventory = _work_order_inventory(state)
    entry = _push_inventory_quantity(
        inventory,
        match_key,
        quantity=1,
        received_at=received_at,
        source=source,
        product_code=product_code,
        stock_code=stock_code,
        stock_name=stock_name,
        color=color,
    )
    item_ids = _inventory_item_ids(entry)
    if item_id and item_id not in item_ids:
        item_ids.append(item_id)
        entry["itemIds"] = item_ids
        entry["quantity"] = max(max(0, round(_numeric(entry.get("quantity")))), len(item_ids))
    item["work_order_id"] = ""
    item["work_order_match_key"] = ""
    item["inventoryAction"] = source
    item["inventory_match_key"] = match_key
    item["inventory_backfill_disabled"] = False


def _remove_completed_item_from_inventory(
    state: dict[str, Any],
    item: dict[str, Any],
    *,
    received_at: str,
    source: str,
) -> bool:
    match_key = str(item.get("inventory_match_key") or "").strip()
    if not match_key:
        item["inventory_match_key"] = ""
        item["inventoryAction"] = source
        return False
    inventory = _work_order_inventory(state)
    entry = inventory.get(match_key)
    if isinstance(entry, dict):
        item_id = str(item.get("item_id") or "").strip()
        item_ids = _inventory_item_ids(entry)
        if item_id:
            entry["itemIds"] = [value for value in item_ids if value != item_id]
        entry["quantity"] = max(0, round(_numeric(entry.get("quantity"))) - 1)
        entry["quantity"] = max(entry["quantity"], len(entry.get("itemIds") or []))
        entry["lastUpdatedAt"] = received_at
        entry["lastSource"] = source
        if entry["quantity"] <= 0 and not _inventory_item_ids(entry):
            inventory.pop(match_key, None)
    item["inventory_match_key"] = ""
    item["inventoryAction"] = source
    return True


def _sync_completed_item_inventory_eligibility(
    state: dict[str, Any],
    item: dict[str, Any],
    *,
    received_at: str,
    source: str,
) -> str:
    if str(item.get("work_order_id") or "").strip():
        return "work_order_linked"
    if not item.get("completed_at") or _inventory_backfill_disabled(item):
        return "not_eligible"
    classification = _normalize_classification(item.get("classification"))
    if classification == "SCRAP":
        removed = _remove_completed_item_from_inventory(
            state,
            item,
            received_at=received_at,
            source="scrap_excluded",
        )
        if not removed:
            item["inventory_match_key"] = ""
            item["inventoryAction"] = "scrap_excluded"
        return "removed_for_scrap"

    current_action = str(item.get("inventoryAction") or "").strip()
    if current_action in {"off_order_completion", "legacy_inventory_backfill", "quality_override_inventory"} and str(item.get("inventory_match_key") or "").strip():
        return "already_in_inventory"

    match_key = str(item.get("inventory_match_key") or "").strip() or _completed_item_match_key(item)
    if not match_key:
        return "missing_match_key"
    color = _normalize_order_color(item.get("final_color"), item.get("color"), item.get("sensor_color"), match_key)
    product_code = str(item.get("product_code") or item.get("stock_code") or "").strip() or match_key.upper()
    stock_code = str(item.get("stock_code") or item.get("product_code") or "").strip() or product_code or match_key.upper()
    stock_name = str(item.get("stock_name") or "").strip() or (color or match_key).upper()
    _move_completed_item_to_inventory(
        state,
        item,
        match_key=match_key,
        received_at=received_at,
        source=source,
        product_code=product_code,
        stock_code=stock_code,
        stock_name=stock_name,
        color=color,
    )
    return "added_to_inventory"


def _clear_item_work_order_context(item: dict[str, Any], *, updated_at: str = "", inventory_action: str = "") -> None:
    item["work_order_id"] = ""
    item["work_order_match_key"] = ""
    item["inventory_match_key"] = ""
    item["inventoryAction"] = inventory_action
    if updated_at:
        item["updated_at"] = updated_at


def _completed_items_for_work_order(state: dict[str, Any], order_id: str) -> list[dict[str, Any]]:
    normalized_order_id = str(order_id or "").strip()
    if not normalized_order_id:
        return []
    items = state.get("itemsById") if isinstance(state.get("itemsById"), dict) else {}
    related_items = [
        item
        for item in items.values()
        if isinstance(item, dict)
        and str(item.get("work_order_id") or "").strip() == normalized_order_id
        and item.get("completed_at")
    ]
    related_items.sort(
        key=lambda row: (
            str(row.get("completed_at") or ""),
            str(row.get("updated_at") or ""),
            str(row.get("item_id") or ""),
        )
    )
    return related_items


def _mark_work_order_pending_approval_if_ready(state: dict[str, Any], order: dict[str, Any], *, now: datetime, completed_at: str) -> bool:
    _sync_work_order_row(order)
    if order.get("status") != "active":
        return False
    if max(0, round(_numeric(order.get("remainingQty")))) > 0:
        return False
    stamp = completed_at or _pseudo_iso_text(now)
    order["status"] = "pending_approval"
    order["autoCompletedAt"] = stamp
    order["completedAt"] = ""
    work_orders = _work_orders_state(state)
    work_orders["activeOrderId"] = str(order.get("orderId") or "")
    metrics = _persist_work_order_metrics(state, order, now=now)
    work_orders["transitionLog"] = _prepend_capped(
        work_orders["transitionLog"],
        _work_order_log_row(
            order,
            event_type="auto_completed",
            stamp=stamp,
            note=(
                "Is emri otomatik tamamlandi. Operator onayi bekleniyor. "
                f"PERF={round(metrics['performance'] * 100.0, 1)}% | "
                f"KALITE={round(metrics['quality'] * 100.0, 1)}% | "
                f"Plansiz Durus={round(metrics['unplannedMs'] / 60000.0, 1)} dk"
            ),
        ),
    )
    _set_summary(
        state,
        f"{order.get('orderId') or 'Is emri'} otomatik tamamlandi. Operator onayi bekleniyor.",
        now=now,
    )
    return True


def _work_order_completion_counts_toward_fulfillment(classification: Any) -> bool:
    return _normalize_classification(classification) == "GOOD"


def _find_work_order_requirement_by_match(order: dict[str, Any] | None, match_key: str) -> dict[str, Any] | None:
    normalized_match = str(match_key or "").strip().lower()
    if not normalized_match or not isinstance(order, dict):
        return None
    for requirement in _work_order_requirements(order):
        if _work_order_requirement_match_key(requirement).lower() == normalized_match:
            return requirement
    return None


def _consume_inventory_for_order(state: dict[str, Any], order: dict[str, Any], *, now: datetime, reason: str = "inventory") -> int:
    inventory = _work_order_inventory(state)
    items = state.get("itemsById") if isinstance(state.get("itemsById"), dict) else {}
    _sync_work_order_row(order)
    total_taken = 0
    notes: list[str] = []
    for requirement in _work_order_requirements(order):
        match_key = _work_order_requirement_match_key(requirement)
        if not match_key:
            continue
        entry = inventory.get(match_key)
        if not isinstance(entry, dict):
            continue
        take_qty = min(
            max(0, round(_numeric(entry.get("quantity")))),
            max(0, round(_numeric(requirement.get("remainingQty")))),
        )
        if take_qty <= 0:
            continue
        taken_item_ids = _inventory_take_item_ids(entry, take_qty)
        entry["quantity"] = max(0, round(_numeric(entry.get("quantity"))) - take_qty)
        entry["lastUpdatedAt"] = _pseudo_iso_text(now)
        entry["lastSource"] = "consumed_for_work_order"
        for item_id in taken_item_ids:
            inventory_item = items.get(item_id)
            if not isinstance(inventory_item, dict) or not inventory_item.get("completed_at"):
                continue
            _assign_item_to_work_order(inventory_item, order, requirement, action="consumed_for_work_order")
        if entry["quantity"] <= 0:
            inventory.pop(match_key, None)
        requirement["inventoryConsumedQty"] = max(0, round(_numeric(requirement.get("inventoryConsumedQty")))) + take_qty
        requirement["completedQty"] = max(0, round(_numeric(requirement.get("completedQty")))) + take_qty
        order["lastAllocationAt"] = entry["lastUpdatedAt"]
        total_taken += take_qty
        notes.append(f"{_work_order_requirement_label(requirement)}={take_qty}")
    if total_taken <= 0:
        return 0
    _sync_work_order_row(order)
    _persist_work_order_metrics(state, order, now=now)
    _set_summary(
        state,
        f"{order.get('orderId') or 'Is emri'} icin depodan {total_taken} adet kullanildi ({', '.join(notes)}).",
        now=now,
    )
    _mark_work_order_pending_approval_if_ready(state, order, now=now, completed_at=str(order.get("lastAllocationAt") or _pseudo_iso_text(now)))
    return total_taken


def _route_completed_item_to_work_orders(
    state: dict[str, Any],
    resolved_key: str,
    item: dict[str, Any],
    *,
    received_at: str,
    now: datetime,
) -> None:
    work_orders = _work_orders_state(state)
    orders = _work_order_orders(state)
    inventory = _work_order_inventory(state)
    item_color = _normalize_order_color(item.get("final_color"), item.get("color"), item.get("sensor_color"))
    item_id = str(item.get("item_id") or resolved_key)
    active_order_id = str(work_orders.get("activeOrderId") or "")
    active_order = orders.get(active_order_id) if active_order_id else None
    item["inventoryAction"] = ""
    item["work_order_id"] = ""
    item["work_order_match_key"] = ""
    item["inventory_match_key"] = ""

    matching_requirement = _find_matching_requirement(active_order, item_color) if isinstance(active_order, dict) else None
    if isinstance(active_order, dict) and isinstance(matching_requirement, dict):
        matching_requirement["productionQty"] = max(0, round(_numeric(matching_requirement.get("productionQty")))) + 1
        matching_requirement["completedQty"] = max(0, round(_numeric(matching_requirement.get("completedQty")))) + 1
        active_order["lastAllocationAt"] = received_at
        _sync_work_order_row(active_order)
        _assign_item_to_work_order(item, active_order, matching_requirement, action="work_order")
        if not _mark_work_order_pending_approval_if_ready(state, active_order, now=now, completed_at=received_at):
            _set_summary(
                state,
                f"#{item_id} aktif {active_order.get('orderId')} is emrine {item_color} olarak yazildi. Kalan {active_order.get('remainingQty')} adet.",
                now=now,
            )
        return

    match_key = item_color or str(item.get("final_color") or item.get("color") or resolved_key)
    if _normalize_classification(item.get("classification")) == "SCRAP":
        item["inventory_match_key"] = ""
        item["inventoryAction"] = "scrap_excluded"
        _set_summary(
            state,
            f"#{item_id} hurda olarak isaretli oldugu icin depoya alinmadi.",
            now=now,
        )
        return
    _move_completed_item_to_inventory(
        state,
        item,
        match_key=match_key,
        received_at=received_at,
        source="off_order_completion",
        product_code=match_key.upper(),
        stock_code=match_key.upper(),
        stock_name=(item_color or match_key).upper(),
        color=item_color,
    )
    _set_summary(
        state,
        f"#{item_id} aktif is emrine uymadigi icin depoya alindi ({match_key}).",
        now=now,
    )


def _recompute_item_counts(state: dict[str, Any]) -> None:
    counts = {
        "total": 0,
        "good": 0,
        "rework": 0,
        "scrap": 0,
        "byColor": {
            "red": empty_color_counts(),
            "yellow": empty_color_counts(),
            "blue": empty_color_counts(),
        },
    }
    items = state.get("itemsById") if isinstance(state.get("itemsById"), dict) else {}
    for item in items.values():
        if not isinstance(item, dict) or not item.get("completed_at") or not bool(item.get("count_in_oee")):
            continue
        classification = _normalize_classification(item.get("classification"))
        bucket_name = _classification_bucket_name(classification)
        color = str(item.get("final_color") or item.get("color") or "").strip().lower()
        if color not in counts["byColor"]:
            continue
        counts["total"] += 1
        counts[bucket_name] += 1
        counts["byColor"][color]["total"] += 1
        counts["byColor"][color][bucket_name] += 1
    state["counts"] = counts


def _queue_order(state: dict[str, Any]) -> list[str]:
    queue_order = state.get("queueOrder")
    if not isinstance(queue_order, list):
        queue_order = []
        state["queueOrder"] = queue_order
    return queue_order


def _vision_state(state: dict[str, Any]) -> dict[str, Any]:
    vision = state.get("vision")
    if not isinstance(vision, dict):
        vision = default_runtime_state()["vision"]
        state["vision"] = vision
    metrics = vision.get("metrics")
    if not isinstance(metrics, dict):
        metrics = default_runtime_state()["vision"]["metrics"]
        vision["metrics"] = metrics
    return vision


def _append_recent_id(state: dict[str, Any], item_key: str) -> None:
    if not item_key:
        return
    recent_ids = state.get("recentItemIds")
    if not isinstance(recent_ids, list):
        recent_ids = []
    recent_ids = [item_key] + [value for value in recent_ids if value != item_key]
    state["recentItemIds"] = recent_ids[:10]


def _archived_item_key(items: dict[str, dict[str, Any]], item_key: str, *, suffix: str = "") -> str:
    raw_suffix = "".join(ch for ch in str(suffix or "") if ch.isdigit()) or str(int(time.time() * 1000))
    base = f"archived:{item_key}:{raw_suffix}"
    candidate = base
    index = 1
    while candidate in items:
        candidate = f"{base}:{index}"
        index += 1
    return candidate


def _archive_completed_item(
    state: dict[str, Any],
    items: dict[str, dict[str, Any]],
    item_key: str,
    *,
    archived_at: str = "",
) -> str:
    item = items.get(item_key)
    if not isinstance(item, dict):
        return ""

    archive_key = _archived_item_key(
        items,
        item_key,
        suffix=str(item.get("completed_at") or item.get("updated_at") or archived_at or item.get("item_id") or item_key),
    )
    items[archive_key] = dict(item)

    recent_ids = state.get("recentItemIds")
    if isinstance(recent_ids, list):
        state["recentItemIds"] = [archive_key if value == item_key else value for value in recent_ids]

    inventory = _work_order_inventory(state)
    for entry in inventory.values():
        if not isinstance(entry, dict):
            continue
        item_ids = _inventory_item_ids(entry)
        if item_key not in item_ids:
            continue
        replaced_ids: list[str] = []
        seen_ids: set[str] = set()
        for value in item_ids:
            normalized = archive_key if value == item_key else value
            if not normalized or normalized in seen_ids:
                continue
            replaced_ids.append(normalized)
            seen_ids.add(normalized)
        entry["itemIds"] = replaced_ids
        entry["quantity"] = max(max(0, round(_numeric(entry.get("quantity")))), len(replaced_ids))
    return archive_key


def _prepare_item_for_new_cycle(
    state: dict[str, Any],
    items: dict[str, dict[str, Any]],
    item_key: str,
    *,
    received_at: str,
) -> dict[str, Any]:
    item = items.get(item_key, {})
    if not isinstance(item, dict):
        item = {}
    if item.get("completed_at"):
        _archive_completed_item(state, items, item_key, archived_at=received_at)
        item = {}
        items[item_key] = item
    return item


def _resolve_item_lookup_key(items: dict[str, dict[str, Any]], item_id: str, *, completed_only: bool = False) -> str:
    normalized_item_id = str(item_id or "").strip()
    if not normalized_item_id:
        return ""

    direct = items.get(normalized_item_id)
    if isinstance(direct, dict) and (not completed_only or direct.get("completed_at")):
        return normalized_item_id

    candidates: list[tuple[str, dict[str, Any]]] = []
    for item_key, item in items.items():
        if not isinstance(item, dict):
            continue
        if str(item.get("item_id") or "").strip() != normalized_item_id:
            continue
        if completed_only and not item.get("completed_at"):
            continue
        candidates.append((item_key, item))
    if not candidates:
        return ""
    candidates.sort(
        key=lambda row: (
            str(row[1].get("completed_at") or ""),
            str(row[1].get("updated_at") or ""),
            str(row[0]),
        ),
        reverse=True,
    )
    return candidates[0][0]


def _head_item_key(state: dict[str, Any]) -> str:
    for item_key in list(_queue_order(state)):
        if item_key:
            return item_key
    return ""


def _remove_queue_item(state: dict[str, Any], item_key: str) -> None:
    state["queueOrder"] = [value for value in _queue_order(state) if value != item_key]


def _processed_vision_keys(state: dict[str, Any]) -> list[str]:
    keys = state.get("processedVisionEventKeys")
    if not isinstance(keys, list):
        keys = []
        state["processedVisionEventKeys"] = keys
    return keys


def _remember_processed_vision_key(state: dict[str, Any], key: str) -> None:
    if not key:
        return
    keys = [value for value in _processed_vision_keys(state) if value != key]
    keys.insert(0, key)
    state["processedVisionEventKeys"] = keys[:100]


def _vision_confidence_tier(confidence: Any) -> str:
    score = _numeric(confidence)
    if score >= 0.8:
        return "high"
    if score >= 0.6:
        return "medium"
    return "low"


def _remaining_travel_ms(item: dict[str, Any], *, now: datetime) -> int:
    queued_at = _parse_iso(str(item.get("queued_at") or item.get("detected_at") or ""))
    travel_ms = max(0, round(_numeric(item.get("travel_ms_initial") or item.get("travel_ms") or 0)))
    if queued_at is None or travel_ms <= 0:
        return travel_ms
    elapsed_ms = max(0, int((now - queued_at).total_seconds() * 1000))
    return max(0, travel_ms - elapsed_ms)


def _desired_vision_health(
    vision: dict[str, Any],
    *,
    now: datetime,
    heartbeat_timeout_sec: int,
    degraded_fps: float,
    degraded_latency_ratio: float,
    decision_deadline_ms: int,
) -> str:
    last_heartbeat = _parse_iso(str(vision.get("lastHeartbeatAt") or ""))
    if last_heartbeat is None or (now - last_heartbeat).total_seconds() > max(1, heartbeat_timeout_sec * 2):
        return "offline"

    fps = max(0.0, _numeric(vision.get("fps")))
    latency_ms = vision.get("eventLatencyMs")
    if fps and fps < degraded_fps:
        return "degraded"
    if latency_ms not in (None, "") and _numeric(latency_ms) > (decision_deadline_ms * degraded_latency_ratio):
        return "degraded"
    return "online"


def _update_vision_health(
    state: dict[str, Any],
    *,
    now: datetime,
    heartbeat_timeout_sec: int,
    degraded_fps: float,
    degraded_latency_ratio: float,
    decision_deadline_ms: int,
    bad_window_threshold: int,
    recovery_window_threshold: int,
) -> bool:
    vision = _vision_state(state)
    desired = _desired_vision_health(
        vision,
        now=now,
        heartbeat_timeout_sec=heartbeat_timeout_sec,
        degraded_fps=degraded_fps,
        degraded_latency_ratio=degraded_latency_ratio,
        decision_deadline_ms=decision_deadline_ms,
    )
    current = str(vision.get("healthState") or "offline")
    changed = False

    if desired == "online":
        vision["badWindows"] = 0
        vision["goodWindows"] = max(0, round(_numeric(vision.get("goodWindows")))) + 1
        if current != "online" and vision["goodWindows"] >= recovery_window_threshold:
            vision["healthState"] = "online"
            changed = True
    else:
        vision["goodWindows"] = 0
        vision["badWindows"] = max(0, round(_numeric(vision.get("badWindows")))) + 1
        if current == "online" and vision["badWindows"] >= bad_window_threshold:
            vision["healthState"] = desired
            changed = True
        elif current == "degraded" and desired == "offline" and vision["badWindows"] >= bad_window_threshold:
            vision["healthState"] = "offline"
            changed = True
        elif current not in {"online", "degraded", "offline"} and vision["badWindows"] >= bad_window_threshold:
            vision["healthState"] = desired
            changed = True

    if current == "offline" and desired == "degraded":
        # Offline durumdan kismi toparlanma tek pencereyle kabul edilmez.
        vision["goodWindows"] = 0
    return changed


def build_live_snapshot(state: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    stamp = _local_datetime(now) or datetime.now().astimezone()
    counts = state.get("counts") if isinstance(state.get("counts"), dict) else {}
    shift = state.get("shift") if isinstance(state.get("shift"), dict) else {}
    total = max(0, round(_numeric(counts.get("total"))))
    good = max(0, round(_numeric(counts.get("good"))))
    rework = max(0, round(_numeric(counts.get("rework"))))
    scrap = max(0, round(_numeric(counts.get("scrap"))))

    shift_active = bool(shift.get("active") and shift.get("startedAt"))
    started_at = _local_datetime(_parse_iso(str(shift.get("startedAt") or "")))
    plan_start = _local_datetime(_parse_iso(str(shift.get("planStart") or "")))
    plan_end = _local_datetime(_parse_iso(str(shift.get("planEnd") or "")))
    elapsed_ms = int((stamp - started_at).total_seconds() * 1000) if shift_active and started_at is not None else 0
    shift_window_total_ms = 0
    if shift_active:
        window_start = started_at
        if window_start is None:
            window_start = plan_start
        if window_start is not None and plan_end is not None:
            shift_window_total_ms = max(0, int((plan_end - window_start).total_seconds() * 1000))
        elif elapsed_ms > 0:
            shift_window_total_ms = elapsed_ms

    active_fault_ms = _active_fault_duration_ms(state, now=stamp) if shift_active else 0
    active_closing_maintenance_ms = _active_planned_maintenance_ms(state, now=stamp) if shift_active else 0

    configured_planned_stop_total_ms = min(
        _duration_ms(
            _first_present(
                shift.get("plannedStopMs"),
                state.get("plannedStopMs"),
                shift.get("plannedStopMin"),
                state.get("plannedStopMin"),
            ),
            multiplier=60_000.0 if _first_present(shift.get("plannedStopMs"), state.get("plannedStopMs")) in (None, "") else 1.0,
        ),
        shift_window_total_ms if shift_window_total_ms > 0 else max(0, elapsed_ms),
    )
    planned_stop_total_ms = min(
        shift_window_total_ms if shift_window_total_ms > 0 else max(0, elapsed_ms),
        configured_planned_stop_total_ms + active_closing_maintenance_ms + max(0, round(_numeric((_maintenance_state(state)).get("closingChecklistDurationMs")))),
    )
    if planned_stop_total_ms > 0 and shift_window_total_ms > 0:
        planned_stop_budget_ms = min(
            planned_stop_total_ms,
            max(0, round(planned_stop_total_ms * min(1.0, elapsed_ms / shift_window_total_ms))),
        )
    else:
        planned_stop_budget_ms = min(planned_stop_total_ms, max(0, elapsed_ms))
    planned_production_total_ms = max(0, shift_window_total_ms - planned_stop_total_ms)
    planned_production_elapsed_ms = max(0, elapsed_ms - planned_stop_budget_ms)
    unplanned_ms = max(0, round(_numeric(state.get("unplannedDowntimeMs")))) + active_fault_ms
    runtime_ms = max(0, planned_production_elapsed_ms - unplanned_ms)
    availability = (runtime_ms / planned_production_elapsed_ms) if planned_production_elapsed_ms > 0 else 0.0
    quality = (good / total) if total > 0 else 1.0

    expected = 0.0
    performance = 0.0
    target_text = "-"
    performance_mode = str(shift.get("performanceMode") or state.get("performanceMode") or "TARGET").upper()
    target_qty = max(0, round(_numeric(_first_present(shift.get("targetQty"), state.get("targetQty")))))
    ideal_cycle_ms = _duration_ms(
        _first_present(
            shift.get("idealCycleMs"),
            state.get("idealCycleMs"),
            shift.get("idealCycleSec"),
            state.get("idealCycleSec"),
        ),
        multiplier=1000.0 if _first_present(shift.get("idealCycleMs"), state.get("idealCycleMs")) in (None, "") else 1.0,
        default=10_000,
    )
    ideal_cycle_sec = _seconds_from_ms(ideal_cycle_ms)

    if performance_mode == "IDEAL_CYCLE" and ideal_cycle_sec > 0:
        expected = (runtime_ms / ideal_cycle_ms) if runtime_ms > 0 else 0.0
        performance = (total / expected) if expected > 0 else 0.0
        target_text = f"{ideal_cycle_sec:.1f} sn cycle / beklenen {expected:.1f}"
    elif target_qty > 0:
        if planned_production_total_ms > 0:
            target_progress = max(0.0, min(1.0, planned_production_elapsed_ms / planned_production_total_ms))
            expected = float(target_qty) * target_progress
        elif shift_active and planned_production_elapsed_ms > 0:
            expected = float(target_qty)
        else:
            expected = 0.0
        performance = (total / expected) if expected > 0 else 0.0
        target_text = f"{target_qty} adet vardiya hedefi / beklenen {expected:.1f}"

    performance = max(0.0, min(1.0, performance))
    oee = availability * performance * quality
    loss = (((scrap + rework) / total) * 100.0) if total > 0 else 0.0
    remaining_ms = max(0, int((plan_end - stamp).total_seconds() * 1000)) if shift_active and plan_end is not None else 0
    gap = round(expected - total, 1) if expected > 0 else None

    by_color = counts.get("byColor") if isinstance(counts.get("byColor"), dict) else {}
    color_summary: dict[str, dict[str, float | int]] = {}
    for color in ("red", "yellow", "blue"):
        bucket = by_color.get(color) if isinstance(by_color.get(color), dict) else {}
        color_total = max(0, round(_numeric(bucket.get("total"))))
        color_good = max(0, round(_numeric(bucket.get("good"))))
        color_rework = max(0, round(_numeric(bucket.get("rework"))))
        color_scrap = max(0, round(_numeric(bucket.get("scrap"))))
        color_summary[color] = {
            "total": color_total,
            "good": color_good,
            "rework": color_rework,
            "scrap": color_scrap,
            "qualityPct": (color_good / color_total * 100.0) if color_total > 0 else 100.0,
            "lossPct": ((color_rework + color_scrap) / color_total * 100.0) if color_total > 0 else 0.0,
        }

    return {
        "shiftActive": shift_active,
        "total": total,
        "good": good,
        "rework": rework,
        "scrap": scrap,
        "availability": availability,
        "performance": performance,
        "quality": quality,
        "oee": oee,
        "expected": expected,
        "gap": gap,
        "elapsedMs": elapsed_ms,
        "plannedStopMs": planned_stop_total_ms,
        "plannedStopBudgetMs": planned_stop_budget_ms,
        "plannedProductionElapsedMs": planned_production_elapsed_ms,
        "plannedProductionTotalMs": planned_production_total_ms,
        "runtimeMs": runtime_ms,
        "unplannedMs": unplanned_ms,
        "activeFaultMs": active_fault_ms,
        "remainingMs": remaining_ms,
        "targetText": target_text,
        "perfMode": performance_mode,
        "lossPct": loss,
        "colorSummary": color_summary,
    }


def _next_snapshot_time_text(trend_rows: list[Any], stamp: datetime) -> str:
    candidate = stamp
    recent_times = {
        str(row.get("time") or "").strip()
        for row in trend_rows[-5:]
        if isinstance(row, dict)
    }
    candidate_text = _pseudo_iso_text(candidate)
    while candidate_text in recent_times:
        candidate = candidate + timedelta(milliseconds=1)
        candidate_text = _pseudo_iso_text(candidate)
    return candidate_text


def _append_oee_trend_snapshot(
    state: dict[str, Any],
    *,
    now: datetime,
    reason: str,
    force: bool = False,
    snapshot: dict[str, Any] | None = None,
) -> bool:
    stamp = _local_datetime(now) or datetime.now().astimezone()
    trend = state["trend"] if isinstance(state.get("trend"), list) else []
    last_logged = _local_datetime(_parse_iso(str(state.get("lastSnapshotLoggedAt") or "")))
    if not force and last_logged is not None and (stamp - last_logged).total_seconds() < OEE_TREND_INTERVAL_SEC:
        return False

    resolved_snapshot = snapshot if isinstance(snapshot, dict) else build_live_snapshot(state, now=stamp)
    if not resolved_snapshot.get("shiftActive") and reason != "shift_stop":
        return False

    color_summary = resolved_snapshot.get("colorSummary") if isinstance(resolved_snapshot.get("colorSummary"), dict) else {}
    blue = color_summary.get("blue") if isinstance(color_summary.get("blue"), dict) else {}
    yellow = color_summary.get("yellow") if isinstance(color_summary.get("yellow"), dict) else {}
    red = color_summary.get("red") if isinstance(color_summary.get("red"), dict) else {}
    snapshot_time = _next_snapshot_time_text(trend, stamp)
    trend.append(
        {
            "time": snapshot_time,
            "reason": str(reason or "").strip().lower() or "periodic_30s",
            "summary": str(state.get("lastEventSummary") or "").strip(),
            "oee": round(float(resolved_snapshot.get("oee") or 0.0) * 100.0, 1),
            "availability": round(float(resolved_snapshot.get("availability") or 0.0) * 100.0, 1),
            "performance": round(float(resolved_snapshot.get("performance") or 0.0) * 100.0, 1),
            "quality": round(float(resolved_snapshot.get("quality") or 0.0) * 100.0, 1),
            "loss": round(float(resolved_snapshot.get("lossPct") or 0.0), 1),
            "mavi_s": max(0, round(_numeric(blue.get("good")))),
            "mavi_r": max(0, round(_numeric(blue.get("rework")))),
            "mavi_h": max(0, round(_numeric(blue.get("scrap")))),
            "sari_s": max(0, round(_numeric(yellow.get("good")))),
            "sari_r": max(0, round(_numeric(yellow.get("rework")))),
            "sari_h": max(0, round(_numeric(yellow.get("scrap")))),
            "kirmizi_s": max(0, round(_numeric(red.get("good")))),
            "kirmizi_r": max(0, round(_numeric(red.get("rework")))),
            "kirmizi_h": max(0, round(_numeric(red.get("scrap")))),
        }
    )
    state["trend"] = trend[-OEE_TREND_HISTORY_LIMIT:]
    state["lastSnapshotLoggedAt"] = snapshot_time
    state["lastUpdatedAt"] = snapshot_time
    return True


def _overlap_ms(start_at: datetime, end_at: datetime, window_start: datetime, window_end: datetime) -> int:
    latest_start = max(start_at, window_start)
    earliest_end = min(end_at, window_end)
    if earliest_end <= latest_start:
        return 0
    return max(0, int((earliest_end - latest_start).total_seconds() * 1000))


def _work_order_fault_ms(state: dict[str, Any], *, start_at: datetime, end_at: datetime) -> int:
    total_ms = 0
    fault_history = state.get("faultHistory") if isinstance(state.get("faultHistory"), list) else []
    for row in fault_history:
        if not isinstance(row, dict):
            continue
        fault_start = _parse_iso(str(row.get("startedAt") or ""))
        fault_end = _parse_iso(str(row.get("endedAt") or ""))
        if fault_start is None or fault_end is None:
            continue
        total_ms += _overlap_ms(fault_start, fault_end, start_at, end_at)
    active_fault = state.get("activeFault") if isinstance(state.get("activeFault"), dict) else None
    if isinstance(active_fault, dict):
        fault_start = _parse_iso(str(active_fault.get("startedAt") or ""))
        if fault_start is not None:
            total_ms += _overlap_ms(fault_start, end_at, start_at, end_at)
    return total_ms


def build_work_order_snapshot(state: dict[str, Any], order: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    stamp = now or datetime.now().astimezone()
    if stamp.tzinfo is None:
        stamp = stamp.astimezone()
    order_id = str(order.get("orderId") or "").strip()
    items = state.get("itemsById") if isinstance(state.get("itemsById"), dict) else {}
    related_items = [
        item
        for item in items.values()
        if isinstance(item, dict)
        and str(item.get("work_order_id") or "").strip() == order_id
        and item.get("completed_at")
    ]
    good = 0
    rework = 0
    scrap = 0
    for item in related_items:
        classification = _normalize_classification(item.get("classification"))
        if classification == "REWORK":
            rework += 1
        elif classification == "SCRAP":
            scrap += 1
        else:
            good += 1
    total = good + rework + scrap
    persisted_good = max(0, round(_numeric(order.get("goodQty"))))
    persisted_rework = max(0, round(_numeric(order.get("reworkQty"))))
    persisted_scrap = max(0, round(_numeric(order.get("scrapQty"))))
    persisted_total = persisted_good + persisted_rework + persisted_scrap
    status = str(order.get("status") or "")
    if persisted_total > total and status in {"pending_approval", "completed"}:
        good = persisted_good
        rework = persisted_rework
        scrap = persisted_scrap
        total = persisted_total
    requirements = _work_order_requirements(order)
    if requirements:
        target_qty = sum(max(0, round(_numeric(requirement.get("quantity")))) for requirement in requirements)
        inventory_consumed_qty = sum(max(0, round(_numeric(requirement.get("inventoryConsumedQty")))) for requirement in requirements)
        production_qty = max(total, sum(max(0, round(_numeric(requirement.get("productionQty")))) for requirement in requirements))
        completed_qty = sum(max(0, round(_numeric(requirement.get("completedQty")))) for requirement in requirements)
        remaining_qty = sum(max(0, round(_numeric(requirement.get("remainingQty")))) for requirement in requirements)
    else:
        target_qty = max(0, round(_numeric(order.get("quantity"))))
        inventory_consumed_qty = max(0, round(_numeric(order.get("inventoryConsumedQty"))))
        production_qty = max(total, round(_numeric(order.get("productionQty"))))
        completed_qty = max(0, round(_numeric(order.get("completedQty"))))
        remaining_raw = order.get("remainingQty")
        remaining_qty = None if remaining_raw in (None, "") else max(0, round(_numeric(remaining_raw)))
    fulfilled_candidates = [completed_qty, production_qty + inventory_consumed_qty]
    if remaining_qty is not None:
        fulfilled_candidates.append(target_qty - remaining_qty)
    fulfilled_qty = min(target_qty, max(fulfilled_candidates) if fulfilled_candidates else 0)
    ideal_cycle_ms = _first_positive_duration_ms(
        (order.get("cycleTimeMs"), 1.0),
        (order.get("cycleTimeSec"), 1000.0),
        (state.get("idealCycleMs"), 1.0),
        (state.get("idealCycleSec"), 1000.0),
        default=10_000,
    )
    if ideal_cycle_ms <= 0:
        ideal_cycle_ms = 10_000
    ideal_cycle_sec = _seconds_from_ms(ideal_cycle_ms)
    planned_duration_ms = int(target_qty * ideal_cycle_ms)
    started_at = _parse_iso(str(order.get("startedAt") or ""))
    auto_completed_at = _parse_iso(str(order.get("autoCompletedAt") or ""))
    completed_at = _parse_iso(str(order.get("completedAt") or ""))
    end_at = (
        auto_completed_at
        if status in {"pending_approval", "completed"} and auto_completed_at is not None
        else completed_at or stamp
    )
    elapsed_ms = int((end_at - started_at).total_seconds() * 1000) if started_at is not None and end_at >= started_at else 0
    unplanned_ms = _work_order_fault_ms(state, start_at=started_at, end_at=end_at) if started_at is not None and elapsed_ms > 0 else 0
    runtime_ms = max(0, elapsed_ms - unplanned_ms)
    availability = (runtime_ms / elapsed_ms) if elapsed_ms > 0 else None
    if availability is not None:
        availability = max(0.0, min(1.0, availability))
    performance = ((production_qty * ideal_cycle_ms) / runtime_ms) if runtime_ms > 0 else 0.0
    performance = max(0.0, min(1.0, performance))
    quality = (good / total) if total > 0 else 1.0
    quality = max(0.0, min(1.0, quality))
    oee = (availability * performance * quality) if availability is not None else None
    return {
        "orderId": order_id,
        "targetQty": target_qty,
        "fulfilledQty": fulfilled_qty,
        "productionQty": production_qty,
        "inventoryConsumedQty": inventory_consumed_qty,
        "remainingQty": max(0, target_qty - fulfilled_qty),
        "goodQty": good,
        "reworkQty": rework,
        "scrapQty": scrap,
        "idealCycleMs": ideal_cycle_ms,
        "idealCycleSec": ideal_cycle_sec,
        "plannedDurationMs": planned_duration_ms,
        "elapsedMs": elapsed_ms,
        "runtimeMs": runtime_ms,
        "unplannedMs": unplanned_ms,
        "availability": availability,
        "performance": performance,
        "quality": quality,
        "oee": oee,
    }


def _system_log_line(kind: str, state: dict[str, Any], *, now: datetime) -> str:
    shift = state["shift"]
    if kind == "START":
        return (
            "|Tablet|Sistem| OLAY:VARDIYA_BASLADI"
            f"|VARDIYA:{shift['code']}"
            f"|PLAN_BASLANGIC:{_full_time(shift['planStart'])}"
            f"|PLAN_BITIS:{_full_time(shift['planEnd'])}"
            f"|PERF_MOD:{shift['performanceMode']}"
            f"|HEDEF:{int(shift['targetQty'])}"
            f"|IDEAL_CYCLE_SN:{float(shift['idealCycleSec']):.1f}"
            f"|IDEAL_CYCLE_MS:{int(_numeric(shift.get('idealCycleMs')))}"
            f"|PLANLI_DURUS_DK:{float(shift['plannedStopMin']):.1f}"
            f"|PLANLI_DURUS_MS:{int(_numeric(shift.get('plannedStopMs')))}"
        )
    totals = _summary_counts(state)
    return (
        "|Tablet|Sistem| OLAY:VARDIYA_BITTI"
        f"|VARDIYA:{shift['code']}"
        f"|BITIS:{_short_time(_pseudo_iso_text(now))}"
        f"|TOPLAM:{totals['total']}"
        f"|SAGLAM:{totals['good']}"
        f"|REWORK:{totals['rework']}"
        f"|HURDA:{totals['scrap']}"
    )


def _start_shift_runtime(state: dict[str, Any], *, stamp: datetime) -> tuple[str, str]:
    start, end, preset = _shift_window(state["shiftSelected"], stamp)
    state["shift"] = {
        "active": True,
        "code": state["shiftSelected"],
        "name": preset["name"],
        "startedAt": _pseudo_iso_text(stamp),
        "endedAt": "",
        "planStart": _pseudo_iso_text(start),
        "planEnd": _pseudo_iso_text(end),
        "performanceMode": state["performanceMode"],
        "targetQty": state["targetQty"],
        "idealCycleMs": state["idealCycleMs"],
        "idealCycleSec": state["idealCycleSec"],
        "plannedStopMs": state["plannedStopMs"],
        "plannedStopMin": state["plannedStopMin"],
    }
    state["counts"] = {
        "total": 0,
        "good": 0,
        "rework": 0,
        "scrap": 0,
        "byColor": {
            "red": empty_color_counts(),
            "yellow": empty_color_counts(),
            "blue": empty_color_counts(),
        },
    }
    items = state["itemsById"] if isinstance(state.get("itemsById"), dict) else {}
    for item in items.values():
        if isinstance(item, dict):
            item["count_in_oee"] = False
    state["recentItemIds"] = []
    state["activeFault"] = None
    state["faultHistory"] = []
    state["unplannedDowntimeMs"] = 0
    state["manualFaultDurationMs"] = 0
    state["trend"] = []
    state["qualityOverrideLog"] = []
    state["earlyPickRejectLog"] = []
    maintenance = _maintenance_state(state)
    maintenance["openingSession"] = None
    maintenance["closingChecklistDurationMs"] = 0
    maintenance["closingSession"] = None
    vision = _vision_state(state)
    vision["metrics"] = {
        "mismatchCount": 0,
        "earlyAcceptedCount": 0,
        "earlyRejectedCount": 0,
        "lateAuditCount": 0,
    }
    vision["lastRejectReason"] = ""
    state["lastSnapshotLoggedAt"] = ""
    state["lastTabletLine"] = ""
    _set_summary(state, f"{state['shift']['code']} basladi. OEE sayaclari sifirlandi.", now=stamp)
    _append_oee_trend_snapshot(state, now=stamp, reason="shift_start", force=True)
    _refresh_operational_state(state)
    system_line = _system_log_line("START", state, now=stamp)
    return state["lastEventSummary"], system_line


def _stop_shift_runtime(state: dict[str, Any], *, stamp: datetime) -> tuple[str, str]:
    if isinstance(state.get("activeFault"), dict):
        _close_active_fault(state, ended_at=_pseudo_iso_text(stamp))
    _set_summary(state, f"{state['shift']['code']} kapatildi. Vardiya ozeti kilitlendi.", now=stamp)
    final_snapshot = build_live_snapshot(state, now=stamp)
    _append_oee_trend_snapshot(state, now=stamp, reason="shift_stop", force=True, snapshot=final_snapshot)
    system_line = _system_log_line("STOP", state, now=stamp)
    state["shift"]["active"] = False
    state["shift"]["endedAt"] = _pseudo_iso_text(stamp)
    _refresh_operational_state(state)
    return state["lastEventSummary"], system_line


def _complete_runtime_item(
    state: dict[str, Any],
    items: dict[str, dict[str, Any]],
    *,
    resolved_key: str,
    item_id: str,
    measure_id: str,
    color: str,
    parsed: dict[str, Any],
    received_at: str,
    now: datetime,
) -> bool:
    item = items.get(resolved_key, {})
    if item.get("completed_at"):
        return False

    normalized_color = str(item.get("final_color") or item.get("vision_color") or item.get("sensor_color") or color).strip().lower()
    if normalized_color not in {"red", "yellow", "blue"}:
        normalized_color = color if color in {"red", "yellow", "blue"} else str(item.get("sensor_color") or "blue")
    decision_source = str(item.get("decision_source") or ("VISION" if item.get("vision_color") else "SENSOR")).upper()
    finalization_reason = str(item.get("finalization_reason") or "").strip().upper()
    if not finalization_reason:
        if decision_source == "VISION" and item.get("mismatch_flag"):
            finalization_reason = "VISION_CORRECTED_MISMATCH"
        elif decision_source == "VISION":
            finalization_reason = "VISION_HIGH_CONF"
        elif item.get("late_vision_audit_flag"):
            finalization_reason = "SENSOR_LATE_VISION"
        elif item.get("correlation_status") == "IGNORED_LOW_CONF":
            finalization_reason = "SENSOR_LOW_CONF_VISION_IGNORED"
        else:
            finalization_reason = "SENSOR_NO_VISION"
    item.update(
        {
            "item_id": item_id or item.get("item_id") or resolved_key,
            "measure_id": measure_id or item.get("measure_id") or "",
            "color": normalized_color,
            "final_color": normalized_color,
            "decision_source": decision_source,
            "finalization_reason": finalization_reason,
            "review_required": bool(item.get("review_required")) or bool(parsed.get("review_required")),
            "completed_at": received_at,
            "classification": "GOOD",
            "updated_at": received_at,
            "queue_status": "completed",
            "pick_started": True,
            "pick_trigger_source": str(item.get("pick_trigger_source") or parsed.get("trigger_source") or "TIMER").upper(),
            "final_color_frozen_at": received_at,
        }
    )
    items[resolved_key] = item
    _remove_queue_item(state, resolved_key)
    _append_recent_id(state, resolved_key)
    _recompute_item_counts(state)
    _set_summary(state, f"#{item.get('item_id') or resolved_key} tamamlandi ve renk {normalized_color} olarak kilitlendi.", now=now)
    _route_completed_item_to_work_orders(
        state,
        resolved_key,
        item,
        received_at=received_at,
        now=now,
    )
    return True


_RUNTIME_STATE_RETRY_ATTEMPTS = 6
_RUNTIME_STATE_RETRY_BASE_DELAY_SEC = 0.02
_RUNTIME_STATE_LOCKS: dict[str, threading.RLock] = {}
_RUNTIME_STATE_LOCKS_GUARD = threading.Lock()


def _runtime_state_lock_key(path: Path) -> str:
    try:
        return str(path.resolve()).lower()
    except OSError:
        return str(path.absolute()).lower()


def _runtime_state_file_lock(path: Path) -> threading.RLock:
    key = _runtime_state_lock_key(path)
    with _RUNTIME_STATE_LOCKS_GUARD:
        lock = _RUNTIME_STATE_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _RUNTIME_STATE_LOCKS[key] = lock
        return lock


def _runtime_state_retry_delay(attempt: int) -> float:
    return _RUNTIME_STATE_RETRY_BASE_DELAY_SEC * (attempt + 1)


def read_runtime_state_file(path: Path) -> dict[str, Any] | None:
    with _runtime_state_file_lock(path):
        for attempt in range(_RUNTIME_STATE_RETRY_ATTEMPTS):
            if not path.exists():
                return None
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                return None
            except (PermissionError, json.JSONDecodeError):
                if attempt == _RUNTIME_STATE_RETRY_ATTEMPTS - 1:
                    return None
                time.sleep(_runtime_state_retry_delay(attempt))
                continue
            except OSError:
                return None
            return ensure_runtime_state_shape(payload)
    return None


def write_runtime_state_file(path: Path, state: dict[str, Any]) -> None:
    normalized = ensure_runtime_state_shape(state)
    payload = json.dumps(normalized, ensure_ascii=False, indent=2)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _runtime_state_file_lock(path):
        for attempt in range(_RUNTIME_STATE_RETRY_ATTEMPTS):
            temp_path = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
            try:
                temp_path.write_text(payload, encoding="utf-8")
                temp_path.replace(path)
                return
            except PermissionError:
                if attempt == _RUNTIME_STATE_RETRY_ATTEMPTS - 1:
                    raise
                time.sleep(_runtime_state_retry_delay(attempt))
            finally:
                with contextlib.suppress(OSError):
                    temp_path.unlink()


def _state_locked(method: Any) -> Any:
    @wraps(method)
    def wrapper(self: "OeeRuntimeStateManager", *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


class OeeRuntimeStateManager:
    def __init__(
        self,
        path: Path,
        *,
        heartbeat_timeout_sec: int = 10,
        vision_decision_deadline_ms: int = 300,
        min_remaining_travel_ms_for_early_pick: int = 400,
        vision_degraded_fps: float = 8.0,
        vision_degraded_latency_ratio: float = 0.5,
        vision_bad_window_threshold: int = 2,
        vision_recovery_window_threshold: int = 3,
    ) -> None:
        self.path = path
        self._lock = _runtime_state_file_lock(path)
        self.heartbeat_timeout_sec = heartbeat_timeout_sec
        self.vision_decision_deadline_ms = vision_decision_deadline_ms
        self.min_remaining_travel_ms_for_early_pick = min_remaining_travel_ms_for_early_pick
        self.vision_degraded_fps = vision_degraded_fps
        self.vision_degraded_latency_ratio = vision_degraded_latency_ratio
        self.vision_bad_window_threshold = vision_bad_window_threshold
        self.vision_recovery_window_threshold = vision_recovery_window_threshold

    def read_state(self) -> dict[str, Any]:
        payload = read_runtime_state_file(self.path)
        if payload is None:
            return default_runtime_state()
        return payload

    def write_state(self, state: dict[str, Any]) -> None:
        write_runtime_state_file(self.path, state)

    @_state_locked
    def deactivate_active_shift_on_startup(self, *, now: datetime | None = None) -> bool:
        state = self.read_state()
        if not state["shift"]["active"]:
            return False
        stamp = now or datetime.now().astimezone()
        if isinstance(state.get("activeFault"), dict):
            _close_active_fault(state, ended_at=_pseudo_iso_text(stamp))
        state["shift"]["active"] = False
        state["shift"]["endedAt"] = _pseudo_iso_text(stamp)
        _set_summary(state, "Vardiya hazir durumda. Baslatmak icin vardiya baslat tusunu kullanin.", now=stamp)
        self.write_state(state)
        return True

    @_state_locked
    def apply_control(self, action: str, value: Any = None, *, now: datetime | None = None) -> dict[str, Any]:
        stamp = now or datetime.now().astimezone()
        state = self.read_state()
        normalized_action = str(action or "").strip().lower()
        if normalized_action not in {
            "select_shift",
            "set_performance_mode",
            "set_target_qty",
            "set_ideal_cycle_sec",
            "set_ideal_cycle_ms",
            "set_planned_stop_min",
            "set_planned_stop_ms",
            "shift_start",
            "shift_stop",
        }:
            raise ValueError("INVALID_OEE_CONTROL_ACTION")

        recent_log = ""
        system_line = ""

        if normalized_action == "select_shift":
            selected = str(value or "SHIFT-A").strip().upper()
            state["shiftSelected"] = selected if selected in SHIFT_PRESETS else "SHIFT-A"
            _set_summary(state, f"{state['shiftSelected']} secildi.", now=stamp)
            recent_log = f"SYSTEM|OEE|SELECT_SHIFT|{state['shiftSelected']}"

        elif normalized_action == "set_performance_mode":
            state["performanceMode"] = "IDEAL_CYCLE" if str(value or "").strip().upper() == "IDEAL_CYCLE" else "TARGET"
            _touch_shift_config(state)
            mode_text = "Ideal Cycle" if state["performanceMode"] == "IDEAL_CYCLE" else "Hedef Bazli"
            _set_summary(state, f"Performans modu {mode_text} olarak ayarlandi.", now=stamp)
            if state["shift"]["active"]:
                _append_oee_trend_snapshot(state, now=stamp, reason="control:set_performance_mode", force=True)
            recent_log = f"SYSTEM|OEE|SET_PERFORMANCE_MODE|{state['performanceMode']}"

        elif normalized_action == "set_target_qty":
            state["targetQty"] = max(0, round(_numeric(value)))
            _touch_shift_config(state)
            _set_summary(state, f"Hedef {state['targetQty']} adet olarak guncellendi.", now=stamp)
            if state["shift"]["active"]:
                _append_oee_trend_snapshot(state, now=stamp, reason="control:set_target_qty", force=True)
            recent_log = f"SYSTEM|OEE|SET_TARGET_QTY|{state['targetQty']}"

        elif normalized_action == "set_ideal_cycle_sec":
            state["idealCycleMs"] = _duration_ms(value, multiplier=1000.0)
            state["idealCycleSec"] = _seconds_from_ms(state["idealCycleMs"])
            _touch_shift_config(state)
            _set_summary(state, f"Ideal cycle {state['idealCycleSec']:.1f} sn olarak guncellendi.", now=stamp)
            if state["shift"]["active"]:
                _append_oee_trend_snapshot(state, now=stamp, reason="control:set_ideal_cycle_sec", force=True)
            recent_log = f"SYSTEM|OEE|SET_IDEAL_CYCLE_SEC|{state['idealCycleSec']:.1f}"

        elif normalized_action == "set_ideal_cycle_ms":
            state["idealCycleMs"] = _duration_ms(value)
            state["idealCycleSec"] = _seconds_from_ms(state["idealCycleMs"])
            _touch_shift_config(state)
            _set_summary(state, f"Ideal cycle {int(state['idealCycleMs'])} ms olarak guncellendi.", now=stamp)
            if state["shift"]["active"]:
                _append_oee_trend_snapshot(state, now=stamp, reason="control:set_ideal_cycle_ms", force=True)
            recent_log = f"SYSTEM|OEE|SET_IDEAL_CYCLE_MS|{int(state['idealCycleMs'])}"

        elif normalized_action == "set_planned_stop_min":
            state["plannedStopMs"] = _duration_ms(value, multiplier=60_000.0)
            state["plannedStopMin"] = _minutes_from_ms(state["plannedStopMs"])
            _touch_shift_config(state)
            _set_summary(state, f"Planli durus rezervi {state['plannedStopMin']:.1f} dk olarak guncellendi.", now=stamp)
            if state["shift"]["active"]:
                _append_oee_trend_snapshot(state, now=stamp, reason="control:set_planned_stop_min", force=True)
            recent_log = f"SYSTEM|OEE|SET_PLANNED_STOP_MIN|{state['plannedStopMin']:.1f}"

        elif normalized_action == "set_planned_stop_ms":
            state["plannedStopMs"] = _duration_ms(value)
            state["plannedStopMin"] = _minutes_from_ms(state["plannedStopMs"])
            _touch_shift_config(state)
            _set_summary(state, f"Planli durus rezervi {int(state['plannedStopMs'])} ms olarak guncellendi.", now=stamp)
            if state["shift"]["active"]:
                _append_oee_trend_snapshot(state, now=stamp, reason="control:set_planned_stop_ms", force=True)
            recent_log = f"SYSTEM|OEE|SET_PLANNED_STOP_MS|{int(state['plannedStopMs'])}"

        elif normalized_action == "shift_start":
            if state["shift"]["active"]:
                _set_summary(state, "Aktif vardiya bitmeden yeni vardiya baslatilamadi.", now=stamp)
                recent_log = "SYSTEM|OEE|SHIFT_START|REJECTED"
            else:
                _summary, system_line = _start_shift_runtime(state, stamp=stamp)
                recent_log = system_line

        elif normalized_action == "shift_stop":
            if not state["shift"]["active"]:
                _set_summary(state, "Bitirilecek aktif vardiya yok.", now=stamp)
                recent_log = "SYSTEM|OEE|SHIFT_STOP|REJECTED"
            else:
                _summary, system_line = _stop_shift_runtime(state, stamp=stamp)
                recent_log = system_line

        _refresh_operational_state(state)
        self.write_state(state)
        return {
            "state": state,
            "summary": state["lastEventSummary"],
            "recent_log": recent_log,
            "system_line": system_line,
        }

    @_state_locked
    def register_kiosk_device(
        self,
        *,
        device_id: str,
        device_name: str = "",
        device_role: str = "operator_kiosk",
        bound_station_id: str = "",
        operator_id: str = "",
        operator_code: str = "",
        operator_name: str = "",
        now: datetime | None = None,
    ) -> dict[str, Any]:
        stamp = now or datetime.now().astimezone()
        state = self.read_state()
        seen_at = _pseudo_iso_text(stamp)
        _update_device_presence(
            state,
            device_id=device_id,
            device_name=device_name,
            device_role=device_role,
            bound_station_id=bound_station_id,
            operator_id=operator_id,
            operator_code=operator_code,
            operator_name=operator_name,
            seen_at=seen_at,
        )
        _refresh_operational_state(state)
        self.write_state(state)
        return {
            "state": state,
            "device": _device_registry_state(state).get(str(device_id or "").strip(), {}),
            "session": _device_sessions_state(state).get(str(device_id or "").strip(), {}),
        }

    @_state_locked
    def begin_maintenance_session(
        self,
        phase: str,
        *,
        steps: list[dict[str, Any]],
        device_id: str,
        device_name: str = "",
        device_role: str = "operator_kiosk",
        bound_station_id: str = "",
        operator_id: str = "",
        operator_code: str = "",
        operator_name: str = "",
        now: datetime | None = None,
    ) -> dict[str, Any]:
        stamp = now or datetime.now().astimezone()
        state = self.read_state()
        normalized_phase = "closing" if str(phase or "").strip().lower() == "closing" else "opening"
        maintenance = _maintenance_state(state)
        if _active_maintenance_session(state) is not None:
            active_session = _active_maintenance_session(state)
            if isinstance(active_session, dict) and str(active_session.get("phase") or "") == normalized_phase:
                _update_device_presence(
                    state,
                    device_id=device_id,
                    device_name=device_name,
                    device_role=device_role,
                    bound_station_id=bound_station_id,
                    operator_id=operator_id,
                    operator_code=operator_code,
                    operator_name=operator_name,
                    seen_at=_pseudo_iso_text(stamp),
                )
                self.write_state(state)
                return {"state": state, "session": active_session, "summary": state["lastEventSummary"]}
            raise ValueError("ANOTHER_MAINTENANCE_SESSION_ACTIVE")
        if normalized_phase == "opening" and bool(state["shift"]["active"]):
            raise ValueError("SHIFT_ALREADY_ACTIVE")
        if normalized_phase == "closing" and not bool(state["shift"]["active"]):
            raise ValueError("SHIFT_NOT_ACTIVE")
        if normalized_phase == "closing" and isinstance(state.get("activeFault"), dict):
            raise ValueError("ACTIVE_FAULT_EXISTS")

        seen_at = _pseudo_iso_text(stamp)
        _update_device_presence(
            state,
            device_id=device_id,
            device_name=device_name,
            device_role=device_role,
            bound_station_id=bound_station_id,
            operator_id=operator_id,
            operator_code=operator_code,
            operator_name=operator_name,
            seen_at=seen_at,
        )
        normalized_steps = [
            _normalize_checklist_step(
                step,
                fallback_code=f"{normalized_phase}_step_{index}",
                fallback_label=f"{normalized_phase.title()} Step {index}",
            )
            for index, step in enumerate(steps, start=1)
        ]
        session = {
            "sessionId": uuid.uuid4().hex,
            "phase": normalized_phase,
            "status": "active",
            "deviceId": str(device_id or "").strip(),
            "deviceName": str(device_name or device_id or "").strip(),
            "deviceRole": str(device_role or "operator_kiosk").strip() or "operator_kiosk",
            "boundStationId": str(bound_station_id or "").strip(),
            "operatorId": str(operator_id or "").strip(),
            "operatorCode": str(operator_code or "").strip(),
            "operatorName": str(operator_name or "").strip(),
            "shiftCode": str(state["shift"]["code"] or state["shiftSelected"] or ""),
            "startedAt": seen_at,
            "endedAt": "",
            "durationMs": 0,
            "note": "",
            "steps": normalized_steps,
        }
        if normalized_phase == "opening":
            maintenance["openingSession"] = session
            _set_summary(state, "Acilis bakimi baslatildi.", now=stamp)
        else:
            maintenance["closingSession"] = session
            _set_summary(state, "Kapanis bakimi baslatildi.", now=stamp)
        _refresh_operational_state(state)
        self.write_state(state)
        return {"state": state, "session": session, "summary": state["lastEventSummary"]}

    @_state_locked
    def complete_maintenance_session(
        self,
        phase: str,
        *,
        completed_steps: Any,
        note: str = "",
        device_id: str = "",
        device_name: str = "",
        device_role: str = "operator_kiosk",
        bound_station_id: str = "",
        operator_id: str = "",
        operator_code: str = "",
        operator_name: str = "",
        now: datetime | None = None,
    ) -> dict[str, Any]:
        stamp = now or datetime.now().astimezone()
        state = self.read_state()
        normalized_phase = "closing" if str(phase or "").strip().lower() == "closing" else "opening"
        maintenance = _maintenance_state(state)
        session = _active_maintenance_session(state, phase=normalized_phase)
        if not isinstance(session, dict):
            raise ValueError("MAINTENANCE_SESSION_NOT_FOUND")
        provided_steps: dict[str, dict[str, Any]] = {}
        raw_completed_steps = completed_steps if isinstance(completed_steps, list) else []
        for row in raw_completed_steps:
            if isinstance(row, dict):
                step_code = str(row.get("step_code") or row.get("stepCode") or "").strip()
                if step_code:
                    provided_steps[step_code] = row
            else:
                step_code = str(row or "").strip()
                if step_code:
                    provided_steps[step_code] = {"step_code": step_code}
        if str(device_id or "").strip():
            session["deviceId"] = str(device_id).strip()
        if str(device_name or "").strip():
            session["deviceName"] = str(device_name).strip()
        if str(device_role or "").strip():
            session["deviceRole"] = str(device_role).strip()
        if str(bound_station_id or "").strip():
            session["boundStationId"] = str(bound_station_id).strip()
        if str(operator_id or "").strip():
            session["operatorId"] = str(operator_id).strip()
        if str(operator_code or "").strip():
            session["operatorCode"] = str(operator_code).strip()
        if str(operator_name or "").strip():
            session["operatorName"] = str(operator_name).strip()
        session["note"] = str(note or "").strip()
        for step in session["steps"]:
            step_code = str(step.get("stepCode") or "").strip()
            provided = provided_steps.get(step_code)
            completed = step_code in provided_steps or bool(step.get("completed"))
            if isinstance(provided, dict) and "completed" in provided:
                completed = bool(provided.get("completed"))
            step["completed"] = bool(completed)
            if step["completed"] and not step.get("completedAt"):
                step["completedAt"] = _pseudo_iso_text(stamp)
            if bool(step.get("required")) and not bool(step.get("completed")):
                raise ValueError("MAINTENANCE_STEP_REQUIRED")
        session["endedAt"] = _pseudo_iso_text(stamp)
        session["durationMs"] = _maintenance_session_duration_ms(session, now=stamp)
        session["status"] = "completed"
        seen_at = _pseudo_iso_text(stamp)
        _update_device_presence(
            state,
            device_id=session["deviceId"],
            device_name=session["deviceName"],
            device_role=session["deviceRole"],
            bound_station_id=session["boundStationId"],
            operator_id=session["operatorId"],
            operator_code=session["operatorCode"],
            operator_name=session["operatorName"],
            seen_at=seen_at,
        )
        maintenance["history"] = _prepend_capped(maintenance["history"], dict(session), limit=50)
        system_line = ""
        if normalized_phase == "opening":
            maintenance["openingChecklistDurationMs"] = session["durationMs"]
            maintenance["lastOpeningCompletedAt"] = session["endedAt"]
            maintenance["openingSession"] = None
            _summary, system_line = _start_shift_runtime(state, stamp=stamp)
        else:
            maintenance["closingChecklistDurationMs"] = max(
                0,
                round(_numeric(maintenance.get("closingChecklistDurationMs"))) + session["durationMs"],
            )
            maintenance["lastClosingCompletedAt"] = session["endedAt"]
            maintenance["closingSession"] = None
            _summary, system_line = _stop_shift_runtime(state, stamp=stamp)
        _refresh_operational_state(state)
        self.write_state(state)
        return {
            "state": state,
            "session": session,
            "summary": state["lastEventSummary"],
            "system_line": system_line,
        }

    @_state_locked
    def start_manual_fault(
        self,
        *,
        device_id: str,
        reason_code: str = "",
        reason_text: str = "",
        device_name: str = "",
        device_role: str = "operator_kiosk",
        bound_station_id: str = "",
        operator_id: str = "",
        operator_code: str = "",
        operator_name: str = "",
        now: datetime | None = None,
    ) -> dict[str, Any]:
        stamp = now or datetime.now().astimezone()
        state = self.read_state()
        if not bool(state["shift"]["active"]):
            raise ValueError("SHIFT_NOT_ACTIVE")
        if _active_maintenance_session(state) is not None:
            raise ValueError("MAINTENANCE_SESSION_ACTIVE")
        seen_at = _pseudo_iso_text(stamp)
        _update_device_presence(
            state,
            device_id=device_id,
            device_name=device_name,
            device_role=device_role,
            bound_station_id=bound_station_id,
            operator_id=operator_id,
            operator_code=operator_code,
            operator_name=operator_name,
            seen_at=seen_at,
        )
        if isinstance(state.get("activeFault"), dict):
            raise ValueError("ACTIVE_FAULT_EXISTS")
        active_fault = {
            "faultId": str(int(stamp.timestamp() * 1000)),
            "category": "PLANSIZ_DURUS",
            "reasonCode": str(reason_code or "").strip(),
            "reason": str(reason_text or reason_code or "Bilinmiyor").strip() or "Bilinmiyor",
            "status": "BASLADI",
            "startedAt": seen_at,
            "endedAt": "",
            "durationMs": 0,
            "durationMin": 0.0,
            "source": "kiosk",
            "deviceId": str(device_id or "").strip(),
            "deviceName": str(device_name or device_id or "").strip(),
            "operatorId": str(operator_id or "").strip(),
            "operatorCode": str(operator_code or "").strip(),
            "operatorName": str(operator_name or "").strip(),
            "boundStationId": str(bound_station_id or "").strip(),
            "countsTowardUnplanned": True,
        }
        state["activeFault"] = active_fault
        _set_summary(state, f"Aktif ariza: {active_fault['reason']}", now=stamp)
        _append_oee_trend_snapshot(state, now=stamp, reason="fault_started", force=True)
        _refresh_operational_state(state)
        self.write_state(state)
        return {"state": state, "fault": active_fault, "summary": state["lastEventSummary"]}

    @_state_locked
    def clear_manual_fault(self, *, now: datetime | None = None) -> dict[str, Any]:
        stamp = now or datetime.now().astimezone()
        state = self.read_state()
        active_fault = state.get("activeFault") if isinstance(state.get("activeFault"), dict) else None
        if not isinstance(active_fault, dict) or str(active_fault.get("source") or "").strip().lower() != "kiosk":
            raise ValueError("MANUAL_FAULT_NOT_FOUND")
        ended_at = _pseudo_iso_text(stamp)
        _close_active_fault(state, ended_at=ended_at)
        _set_summary(state, "Manuel ariza kapatildi.", now=stamp)
        _append_oee_trend_snapshot(state, now=stamp, reason="fault_cleared", force=True)
        _refresh_operational_state(state)
        self.write_state(state)
        return {"state": state, "summary": state["lastEventSummary"]}

    @_state_locked
    def request_help(
        self,
        *,
        device_id: str,
        device_name: str = "",
        bound_station_id: str = "",
        line_id: str = "",
        station_name: str = "",
        operator_id: str = "",
        operator_code: str = "",
        operator_name: str = "",
        fault_id: str = "",
        fault_code: str = "",
        reason: str = "",
        fault_started_at: str = "",
        now: datetime | None = None,
    ) -> dict[str, Any]:
        stamp = now or datetime.now().astimezone()
        state = self.read_state()
        seen_at = _pseudo_iso_text(stamp)
        _update_device_presence(
            state,
            device_id=device_id,
            device_name=device_name,
            device_role="operator_kiosk",
            bound_station_id=bound_station_id,
            operator_id=operator_id,
            operator_code=operator_code,
            operator_name=operator_name,
            seen_at=seen_at,
        )
        active_fault = state.get("activeFault") if isinstance(state.get("activeFault"), dict) else {}
        active_fault_matches = False
        if active_fault:
            active_fault_device = str(active_fault.get("deviceId") or "").strip()
            active_fault_station = str(active_fault.get("boundStationId") or "").strip()
            active_fault_matches = (
                bool(active_fault_device and active_fault_device == str(device_id or "").strip())
                or bool(active_fault_station and active_fault_station == str(bound_station_id or "").strip())
                or not str(bound_station_id or "").strip()
            )
        if active_fault_matches:
            fault_id = str(fault_id or active_fault.get("faultId") or "").strip()
            fault_code = str(fault_code or active_fault.get("reasonCode") or "").strip()
            reason = str(reason or active_fault.get("reason") or "").strip()
            fault_started_at = str(fault_started_at or active_fault.get("startedAt") or "").strip()
        help_request = _help_request_state(state)
        request_key = _device_request_key(device_id, bound_station_id)
        request = help_request["requestsByKey"].get(request_key)
        if isinstance(request, dict) and str(request.get("status") or "") in {"open", "acknowledged"}:
            request["repeatCount"] = max(1, round(_numeric(request.get("repeatCount")))) + 1
            request["lastRequestedAt"] = seen_at
            request["deviceName"] = str(device_name or request.get("deviceName") or device_id or "").strip()
            request["boundStationId"] = str(bound_station_id or request.get("boundStationId") or "").strip()
            request["lineId"] = str(line_id or request.get("lineId") or "").strip()
            request["stationName"] = str(station_name or request.get("stationName") or "").strip()
            request["operatorId"] = str(operator_id or request.get("operatorId") or "").strip()
            request["operatorCode"] = str(operator_code or request.get("operatorCode") or "").strip()
            request["operatorName"] = str(operator_name or request.get("operatorName") or "").strip()
            request["faultId"] = str(fault_id or request.get("faultId") or "").strip()
            request["faultCode"] = str(fault_code or request.get("faultCode") or "").strip()
            request["reason"] = str(reason or request.get("reason") or "").strip()
            request["faultStartedAt"] = str(fault_started_at or request.get("faultStartedAt") or "").strip()
        else:
            request = {
                "requestId": uuid.uuid4().hex,
                "requestKey": request_key,
                "lineId": str(line_id or "").strip(),
                "deviceId": str(device_id or "").strip(),
                "deviceName": str(device_name or device_id or "").strip(),
                "boundStationId": str(bound_station_id or "").strip(),
                "stationName": str(station_name or "").strip(),
                "operatorId": str(operator_id or "").strip(),
                "operatorCode": str(operator_code or "").strip(),
                "operatorName": str(operator_name or "").strip(),
                "status": "open",
                "repeatCount": 1,
                "faultId": str(fault_id or "").strip(),
                "faultCode": str(fault_code or "").strip(),
                "reason": str(reason or "").strip(),
                "faultStartedAt": str(fault_started_at or "").strip(),
                "createdAt": seen_at,
                "lastRequestedAt": seen_at,
                "acknowledgedAt": "",
                "resolvedAt": "",
                "technicianName": "",
                "responseDurationMs": 0,
                "repairDurationMs": 0,
                "totalDurationMs": 0,
            }
            help_request["requestsByKey"][request_key] = request
        help_request["history"] = _prepend_capped(help_request["history"], dict(request), limit=50)
        _set_summary(state, "Teknisyen yardim cagri istegi gonderildi.", now=stamp)
        _refresh_operational_state(state)
        self.write_state(state)
        return {"state": state, "request": request, "summary": state["lastEventSummary"]}

    @_state_locked
    def acknowledge_help_request(
        self,
        request_id: str,
        *,
        technician_name: str = "",
        technician_device_id: str = "",
        technician_device_name: str = "",
        now: datetime | None = None,
    ) -> dict[str, Any]:
        stamp = now or datetime.now().astimezone()
        state = self.read_state()
        seen_at = _pseudo_iso_text(stamp)
        if str(technician_device_id or "").strip():
            _update_device_presence(
                state,
                device_id=technician_device_id,
                device_name=technician_device_name,
                device_role="technician_kiosk",
                seen_at=seen_at,
            )
        help_request = _help_request_state(state)
        found = _find_help_request_by_id(help_request, request_id)
        if found is None:
            raise ValueError("HELP_REQUEST_NOT_FOUND")
        _request_key, request = found
        status = str(request.get("status") or "").strip()
        if status == "resolved":
            raise ValueError("HELP_REQUEST_ALREADY_RESOLVED")
        if status not in {"open", "acknowledged"}:
            raise ValueError("HELP_REQUEST_NOT_ACTIVE")
        if not str(request.get("acknowledgedAt") or "").strip():
            request["acknowledgedAt"] = seen_at
        if str(technician_name or "").strip():
            request["technicianName"] = str(technician_name).strip()
        request["status"] = "acknowledged"
        request["responseDurationMs"] = _duration_between_texts(
            request.get("createdAt"),
            request.get("acknowledgedAt"),
        )
        help_request["history"] = _prepend_capped(help_request["history"], dict(request), limit=50)
        _set_summary(state, "Teknisyen yardim cagrisi kabul edildi.", now=stamp)
        _refresh_operational_state(state)
        self.write_state(state)
        return {"state": state, "request": request, "summary": state["lastEventSummary"]}

    @_state_locked
    def resolve_help_request(
        self,
        request_id: str,
        *,
        technician_name: str = "",
        technician_device_id: str = "",
        technician_device_name: str = "",
        now: datetime | None = None,
    ) -> dict[str, Any]:
        stamp = now or datetime.now().astimezone()
        state = self.read_state()
        seen_at = _pseudo_iso_text(stamp)
        if str(technician_device_id or "").strip():
            _update_device_presence(
                state,
                device_id=technician_device_id,
                device_name=technician_device_name,
                device_role="technician_kiosk",
                seen_at=seen_at,
            )
        help_request = _help_request_state(state)
        found = _find_help_request_by_id(help_request, request_id)
        if found is None:
            raise ValueError("HELP_REQUEST_NOT_FOUND")
        _request_key, request = found
        status = str(request.get("status") or "").strip()
        if status == "resolved":
            raise ValueError("HELP_REQUEST_ALREADY_RESOLVED")
        if status not in {"open", "acknowledged"}:
            raise ValueError("HELP_REQUEST_NOT_ACTIVE")
        if not str(request.get("acknowledgedAt") or "").strip():
            request["acknowledgedAt"] = seen_at
        request["resolvedAt"] = seen_at
        if str(technician_name or "").strip():
            request["technicianName"] = str(technician_name).strip()
        request["status"] = "resolved"
        request["responseDurationMs"] = _duration_between_texts(
            request.get("createdAt"),
            request.get("acknowledgedAt"),
        )
        request["repairDurationMs"] = _duration_between_texts(
            request.get("acknowledgedAt"),
            request.get("resolvedAt"),
        )
        request["totalDurationMs"] = _duration_between_texts(
            request.get("createdAt"),
            request.get("resolvedAt"),
        )
        closed_fault: dict[str, Any] | None = None
        active_fault = state.get("activeFault") if isinstance(state.get("activeFault"), dict) else None
        if isinstance(active_fault, dict) and str(active_fault.get("source") or "").strip().lower() == "kiosk":
            request_fault_id = str(request.get("faultId") or "").strip()
            active_fault_id = str(active_fault.get("faultId") or "").strip()
            fault_matches = bool(request_fault_id and request_fault_id == active_fault_id)
            if not fault_matches:
                fault_matches = (
                    str(request.get("deviceId") or "").strip() == str(active_fault.get("deviceId") or "").strip()
                    or str(request.get("boundStationId") or "").strip() == str(active_fault.get("boundStationId") or "").strip()
                )
            if fault_matches:
                closed_fault = dict(active_fault)
                _close_active_fault(state, ended_at=seen_at)
        help_request["history"] = _prepend_capped(help_request["history"], dict(request), limit=50)
        _set_summary(state, "Teknisyen yardim cagrisi cozuldu.", now=stamp)
        _refresh_operational_state(state)
        self.write_state(state)
        return {
            "state": state,
            "request": request,
            "closed_fault": closed_fault,
            "summary": state["lastEventSummary"],
        }

    @_state_locked
    def apply_kiosk_quality_override(
        self,
        item_id: str,
        classification: Any,
        *,
        reason_text: str = "",
        now: datetime | None = None,
    ) -> dict[str, Any]:
        stamp = now or datetime.now().astimezone()
        state = self.read_state()
        items = state["itemsById"] if isinstance(state.get("itemsById"), dict) else {}
        normalized_item_id = str(item_id or "").strip()
        shift_started_at = _parse_iso(str(((state.get("shift") or {}) if isinstance(state.get("shift"), dict) else {}).get("startedAt") or ""))
        require_counted = bool(((state.get("shift") or {}) if isinstance(state.get("shift"), dict) else {}).get("active"))
        visible_item_ids: list[str] = []
        recent_item_keys = state.get("recentItemIds") if isinstance(state.get("recentItemIds"), list) else []
        for raw_key in recent_item_keys:
            item = items.get(str(raw_key or "").strip())
            if not isinstance(item, dict):
                continue
            completed_at = _parse_iso(str(item.get("completed_at") or ""))
            if completed_at is None:
                continue
            if shift_started_at is not None and completed_at < shift_started_at:
                continue
            if require_counted and not bool(item.get("count_in_oee")):
                continue
            candidate_id = str(item.get("item_id") or raw_key or "").strip()
            if not candidate_id or candidate_id in visible_item_ids:
                continue
            visible_item_ids.append(candidate_id)
            if len(visible_item_ids) >= 5:
                break
        if normalized_item_id not in set(visible_item_ids):
            raise ValueError("ITEM_NOT_IN_KIOSK_WINDOW")
        item_key = _resolve_item_lookup_key(items, normalized_item_id, completed_only=True)
        item = items.get(item_key)
        if not isinstance(item, dict):
            raise ValueError("ITEM_NOT_FOUND")
        if not item.get("completed_at"):
            raise ValueError("ITEM_NOT_COMPLETED")
        work_order_id = str(item.get("work_order_id") or "").strip()
        if work_order_id:
            order = _work_order_orders(state).get(work_order_id)
            if not isinstance(order, dict):
                raise ValueError("WORK_ORDER_NOT_FOUND")
            if str(order.get("status") or "").strip() not in {"active", "pending_approval"}:
                raise ValueError("WORK_ORDER_LOCKED_FOR_KIOSK_OVERRIDE")
        result = self.apply_quality_override(normalized_item_id, classification, now=stamp)
        item = result.get("item") if isinstance(result.get("item"), dict) else {}
        override = result.get("override") if isinstance(result.get("override"), dict) else None
        if override is not None:
            override["reason_text"] = str(reason_text or "").strip()
            item["override_reason_text"] = str(reason_text or "").strip()
            self.write_state(result["state"])
        return result

    @_state_locked
    def import_work_orders(
        self,
        payload: Any,
        *,
        replace_existing: bool = True,
        source_folder: str = "",
        source_file: str = "",
        now: datetime | None = None,
    ) -> dict[str, Any]:
        stamp = now or datetime.now().astimezone()
        state = self.read_state()
        work_orders = _work_orders_state(state)
        existing_orders = _work_order_orders(state)
        existing_sequence = list(_work_order_sequence(state))
        raw_orders = payload if isinstance(payload, list) else []
        if not raw_orders:
            raise ValueError("INVALID_WORK_ORDER_PAYLOAD")

        queued_at = _pseudo_iso_text(stamp)
        next_orders: dict[str, dict[str, Any]] = {} if replace_existing else dict(existing_orders)
        incoming_ids: list[str] = []
        for raw_order in raw_orders:
            normalized = _normalize_work_order_row(raw_order, queued_at=queued_at)
            order_id = str(normalized.get("orderId") or "").strip()
            if not order_id:
                raise ValueError("WORK_ORDER_ID_REQUIRED")
            merged = _normalize_work_order_row(
                raw_order,
                existing=existing_orders.get(order_id),
                queued_at=str((existing_orders.get(order_id) or {}).get("queuedAt") or queued_at),
            )
            existing = existing_orders.get(order_id)
            if isinstance(existing, dict) and str(existing.get("status") or "") in {"active", "completed"}:
                merged["status"] = str(existing.get("status") or merged["status"])
                merged["startedAt"] = str(existing.get("startedAt") or merged["startedAt"])
                merged["completedAt"] = str(existing.get("completedAt") or merged["completedAt"])
                merged["startedBy"] = str(existing.get("startedBy") or merged["startedBy"])
                merged["startedByName"] = str(existing.get("startedByName") or merged["startedByName"])
                merged["transitionReason"] = str(existing.get("transitionReason") or merged["transitionReason"])
                merged["inventoryConsumedQty"] = max(
                    round(_numeric(merged.get("inventoryConsumedQty"))),
                    round(_numeric(existing.get("inventoryConsumedQty"))),
                )
                merged["productionQty"] = max(
                    round(_numeric(merged.get("productionQty"))),
                    round(_numeric(existing.get("productionQty"))),
                )
                merged["completedQty"] = max(
                    round(_numeric(merged.get("completedQty"))),
                    round(_numeric(existing.get("completedQty"))),
                )
                merged["lastAllocationAt"] = str(existing.get("lastAllocationAt") or merged.get("lastAllocationAt") or "")
            _sync_work_order_row(merged)
            next_orders[order_id] = merged
            if order_id not in incoming_ids:
                incoming_ids.append(order_id)

        if replace_existing:
            for order_id in existing_sequence:
                existing = existing_orders.get(order_id)
                if not isinstance(existing, dict) or order_id in next_orders:
                    continue
                if str(existing.get("status") or "") in {"active", "completed"}:
                    next_orders[order_id] = existing

        next_sequence: list[str] = []
        for order_id in existing_sequence:
            if order_id in next_orders and order_id not in next_sequence:
                next_sequence.append(order_id)
        for order_id in incoming_ids:
            if order_id in next_orders and order_id not in next_sequence:
                next_sequence.append(order_id)
        for order_id in next_orders:
            if order_id not in next_sequence:
                next_sequence.append(order_id)

        work_orders["ordersById"] = next_orders
        work_orders["orderSequence"] = next_sequence
        if source_folder or source_file:
            work_orders["source"] = {
                "folder": str(source_folder or work_orders.get("source", {}).get("folder") or ""),
                "file": str(source_file or work_orders.get("source", {}).get("file") or ""),
                "loadedAt": queued_at,
            }
        if str(work_orders.get("activeOrderId") or "") not in next_orders:
            work_orders["activeOrderId"] = ""
        if str(work_orders.get("lastCompletedOrderId") or "") not in next_orders:
            work_orders["lastCompletedOrderId"] = ""
            work_orders["lastCompletedAt"] = ""

        queued_count = sum(1 for order in next_orders.values() if str(order.get("status") or "") == "queued")
        _set_summary(state, f"{len(incoming_ids)} is emri yuklendi. Bekleyen kuyruk {queued_count}.", now=stamp)
        self.write_state(state)
        return {
            "state": state,
            "summary": state["lastEventSummary"],
            "queued_count": queued_count,
            "total_count": len(next_orders),
        }

    @_state_locked
    def import_work_orders_from_file(
        self,
        path: Path,
        *,
        replace_existing: bool = True,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ValueError("WORK_ORDER_SOURCE_NOT_FOUND") from exc
        except json.JSONDecodeError as exc:
            raise ValueError("WORK_ORDER_SOURCE_INVALID_JSON") from exc
        orders = payload.get("orders") if isinstance(payload, dict) else payload
        if not isinstance(orders, list):
            raise ValueError("INVALID_WORK_ORDER_PAYLOAD")
        return self.import_work_orders(
            orders,
            replace_existing=replace_existing,
            source_folder=str(path.parent),
            source_file=path.name,
            now=now,
        )

    @_state_locked
    def reorder_work_orders(self, ordered_ids: Any, *, now: datetime | None = None) -> dict[str, Any]:
        stamp = now or datetime.now().astimezone()
        state = self.read_state()
        work_orders = _work_orders_state(state)
        sequence = _work_order_sequence(state)
        orders = _work_order_orders(state)
        requested = [str(value or "").strip() for value in (ordered_ids if isinstance(ordered_ids, list) else [])]
        queued_current = [order_id for order_id in sequence if str(orders.get(order_id, {}).get("status") or "") == "queued"]
        queued_set = {order_id for order_id in queued_current}
        requested_set = {order_id for order_id in requested if order_id}
        if queued_set != requested_set:
            raise ValueError("INVALID_WORK_ORDER_REORDER")
        next_sequence: list[str] = []
        queued_iter = iter(requested)
        for order_id in sequence:
            if order_id in queued_set:
                next_sequence.append(next(queued_iter))
            else:
                next_sequence.append(order_id)
        work_orders["orderSequence"] = next_sequence
        _set_summary(state, "Is emri sirasi guncellendi.", now=stamp)
        self.write_state(state)
        return {
            "state": state,
            "summary": state["lastEventSummary"],
        }

    @_state_locked
    def set_work_order_tolerance(self, minutes: Any, *, now: datetime | None = None) -> dict[str, Any]:
        stamp = now or datetime.now().astimezone()
        state = self.read_state()
        work_orders = _work_orders_state(state)
        work_orders["toleranceMs"] = _duration_ms(minutes, multiplier=60_000.0)
        work_orders["toleranceMinutes"] = _minutes_from_ms(work_orders["toleranceMs"])
        _set_summary(state, f"Is emirleri arasi tolerans {work_orders['toleranceMinutes']:.1f} dk olarak ayarlandi.", now=stamp)
        self.write_state(state)
        return {
            "state": state,
            "summary": state["lastEventSummary"],
            "tolerance_ms": work_orders["toleranceMs"],
            "tolerance_minutes": work_orders["toleranceMinutes"],
        }

    @_state_locked
    def start_work_order(
        self,
        order_id: str,
        *,
        operator_code: str = "",
        operator_name: str = "",
        transition_reason: str = "",
        started_at: str = "",
        now: datetime | None = None,
    ) -> dict[str, Any]:
        stamp = now or datetime.now().astimezone()
        if stamp.tzinfo is None:
            stamp = stamp.astimezone()
        state = self.read_state()
        work_orders = _work_orders_state(state)
        orders = _work_order_orders(state)
        normalized_order_id = str(order_id or "").strip()
        order = orders.get(normalized_order_id)
        if not isinstance(order, dict):
            raise ValueError("WORK_ORDER_NOT_FOUND")
        if str(work_orders.get("activeOrderId") or "").strip():
            raise ValueError("ACTIVE_WORK_ORDER_EXISTS")
        if str(order.get("status") or "") == "completed":
            raise ValueError("WORK_ORDER_ALREADY_COMPLETED")

        start_dt = _parse_iso(started_at) or stamp
        if start_dt.tzinfo is None:
            start_dt = start_dt.astimezone()
        start_text = _pseudo_iso_text(start_dt)
        tolerance_ms = _duration_ms(
            _first_present(work_orders.get("toleranceMs"), work_orders.get("toleranceMinutes")),
            multiplier=60_000.0 if work_orders.get("toleranceMs") in (None, "") else 1.0,
        )
        last_completed_order_id = str(work_orders.get("lastCompletedOrderId") or "").strip()
        last_completed_at = _parse_iso(str(work_orders.get("lastCompletedAt") or ""))
        cleaned_reason = str(transition_reason or "").strip()
        if last_completed_order_id and last_completed_at is not None and tolerance_ms > 0:
            elapsed_ms = max(0, int((start_dt - last_completed_at).total_seconds() * 1000))
            if elapsed_ms > tolerance_ms and not cleaned_reason:
                raise WorkOrderTransitionReasonRequired(
                    order_id=normalized_order_id,
                    previous_order_id=last_completed_order_id,
                    elapsed_ms=elapsed_ms,
                    tolerance_ms=tolerance_ms,
                )

        order["status"] = "active"
        order["startedAt"] = start_text
        order["autoCompletedAt"] = ""
        order["completedAt"] = ""
        order["startedBy"] = str(operator_code or "").strip() or "OPERATOR"
        order["startedByName"] = str(operator_name or "").strip()
        order["transitionReason"] = cleaned_reason
        work_orders["activeOrderId"] = normalized_order_id
        inventory_used = _consume_inventory_for_order(state, order, now=start_dt)
        _persist_work_order_metrics(state, order, now=start_dt)
        work_orders["transitionLog"] = _prepend_capped(
            work_orders["transitionLog"],
            _work_order_log_row(
                order,
                event_type="started",
                stamp=start_text,
                note=cleaned_reason or (f"Depodan {inventory_used} adet dusuldu." if inventory_used else "Operator baslatti."),
            ),
        )
        if str(order.get("status") or "") == "pending_approval":
            _set_summary(
                state,
                f"{normalized_order_id} baslatildi ve otomatik tamamlandi. Operator onayi bekleniyor.",
                now=start_dt,
            )
        else:
            _set_summary(
                state,
                f"{normalized_order_id} baslatildi. Kalan {order.get('remainingQty')} adet.",
                now=start_dt,
            )
        self.write_state(state)
        return {
            "state": state,
            "summary": state["lastEventSummary"],
            "order": order,
            "inventory_used": inventory_used,
        }

    @_state_locked
    def accept_active_work_order(self, *, now: datetime | None = None) -> dict[str, Any]:
        stamp = now or datetime.now().astimezone()
        if stamp.tzinfo is None:
            stamp = stamp.astimezone()
        accepted_text = _pseudo_iso_text(stamp)
        state = self.read_state()
        work_orders = _work_orders_state(state)
        orders = _work_order_orders(state)
        active_order_id = str(work_orders.get("activeOrderId") or "").strip()
        order = orders.get(active_order_id)
        if not active_order_id or not isinstance(order, dict) or str(order.get("status") or "") != "pending_approval":
            raise ValueError("WORK_ORDER_PENDING_APPROVAL_NOT_FOUND")

        order["status"] = "completed"
        order["completedAt"] = accepted_text
        if not str(order.get("autoCompletedAt") or "").strip():
            order["autoCompletedAt"] = str(order.get("lastAllocationAt") or accepted_text)
        work_orders["activeOrderId"] = ""
        work_orders["lastCompletedOrderId"] = active_order_id
        work_orders["lastCompletedAt"] = accepted_text
        metrics = _persist_work_order_metrics(state, order, now=stamp)
        work_orders["completionLog"] = _prepend_capped(
            work_orders["completionLog"],
            _work_order_log_row(
                order,
                event_type="completed",
                stamp=accepted_text,
                note=(
                    "Operator onayi ile kapatildi. "
                    f"Oto Tamam={order.get('autoCompletedAt') or '-'} | "
                    f"PERF={round(metrics['performance'] * 100.0, 1)}% | "
                    f"KALITE={round(metrics['quality'] * 100.0, 1)}% | "
                    f"Plansiz Durus={round(metrics['unplannedMs'] / 60000.0, 1)} dk"
                ),
            ),
        )
        _set_summary(
            state,
            f"{active_order_id} operator onayi ile kapatildi.",
            now=stamp,
        )
        self.write_state(state)
        return {
            "state": state,
            "summary": state["lastEventSummary"],
            "order": order,
        }

    @_state_locked
    def rollback_active_work_order(self, *, now: datetime | None = None) -> dict[str, Any]:
        stamp = now or datetime.now().astimezone()
        if stamp.tzinfo is None:
            stamp = stamp.astimezone()
        rollback_text = _pseudo_iso_text(stamp)
        state = self.read_state()
        work_orders = _work_orders_state(state)
        orders = _work_order_orders(state)
        active_order_id = str(work_orders.get("activeOrderId") or "").strip()
        order = orders.get(active_order_id)
        if not active_order_id or not isinstance(order, dict) or str(order.get("status") or "") not in WORK_ORDER_BLOCKING_STATUSES:
            raise ValueError("ACTIVE_WORK_ORDER_NOT_FOUND")

        _sync_work_order_row(order)
        log_order = dict(order)
        inventory = _work_order_inventory(state)
        tracked_items = _completed_items_for_work_order(state, active_order_id)
        tracked_counts_by_match: dict[str, int] = {}
        for item in tracked_items:
            match_key = (
                str(item.get("work_order_match_key") or "").strip()
                or str(item.get("inventory_match_key") or "").strip()
                or _normalize_order_color(item.get("final_color"), item.get("color"), item.get("sensor_color"))
                or _order_match_key(order)
                or "unknown"
            )
            _move_completed_item_to_inventory(
                state,
                item,
                match_key=match_key,
                received_at=rollback_text,
                source="rollback_to_inventory",
                product_code=str(item.get("product_code") or item.get("final_color") or match_key).upper(),
                stock_code=str(item.get("stock_code") or item.get("final_color") or match_key).upper(),
                stock_name=str(item.get("stock_name") or item.get("final_color") or match_key).upper(),
                color=_normalize_order_color(item.get("final_color"), item.get("color"), item.get("sensor_color")),
            )
            tracked_counts_by_match[match_key] = tracked_counts_by_match.get(match_key, 0) + 1

        anonymous_returned = 0
        tracked_remaining_by_match = dict(tracked_counts_by_match)
        requirements = _work_order_requirements(order)
        if requirements:
            for requirement in requirements:
                match_key = _work_order_requirement_match_key(requirement) or _order_match_key(order) or "unknown"
                completed_qty = max(0, round(_numeric(requirement.get("completedQty"))))
                tracked_for_requirement = min(completed_qty, tracked_remaining_by_match.get(match_key, 0))
                tracked_remaining_by_match[match_key] = max(0, tracked_remaining_by_match.get(match_key, 0) - tracked_for_requirement)
                anonymous_qty = max(0, completed_qty - tracked_for_requirement)
                if anonymous_qty > 0:
                    _push_inventory_quantity(
                        inventory,
                        match_key,
                        quantity=anonymous_qty,
                        received_at=rollback_text,
                        source="rollback_to_inventory",
                        product_code=str(requirement.get("productCode") or ""),
                        stock_code=str(requirement.get("stockCode") or ""),
                        stock_name=str(requirement.get("stockName") or ""),
                        color=str(requirement.get("color") or ""),
                    )
                    anonymous_returned += anonymous_qty
                requirement["inventoryConsumedQty"] = 0
                requirement["productionQty"] = 0
                requirement["completedQty"] = 0
                requirement["remainingQty"] = max(0, round(_numeric(requirement.get("quantity"))))
        else:
            completed_qty = max(0, round(_numeric(order.get("completedQty"))))
            tracked_total = sum(tracked_counts_by_match.values())
            anonymous_qty = max(0, completed_qty - tracked_total)
            if anonymous_qty > 0:
                _push_inventory_quantity(
                    inventory,
                    _order_match_key(order) or "unknown",
                    quantity=anonymous_qty,
                    received_at=rollback_text,
                    source="rollback_to_inventory",
                    product_code=str(order.get("productCode") or ""),
                    stock_code=str(order.get("stockCode") or ""),
                    stock_name=str(order.get("stockName") or ""),
                    color=str(order.get("productColor") or ""),
                )
                anonymous_returned += anonymous_qty
            order["inventoryConsumedQty"] = 0
            order["productionQty"] = 0
            order["completedQty"] = 0
            order["remainingQty"] = max(0, round(_numeric(order.get("quantity"))))

        order["status"] = "queued"
        order["startedAt"] = ""
        order["autoCompletedAt"] = ""
        order["completedAt"] = ""
        order["startedBy"] = ""
        order["startedByName"] = ""
        order["transitionReason"] = ""
        order["lastAllocationAt"] = ""
        work_orders["activeOrderId"] = ""
        _sync_work_order_row(order)
        _persist_work_order_metrics(state, order, now=stamp)

        returned_to_inventory = len(tracked_items) + anonymous_returned
        note = "Aktif is emri kuyruga geri alindi."
        if returned_to_inventory > 0:
            note = f"{returned_to_inventory} adet depoya geri alindi."
            if anonymous_returned > 0:
                note = f"{note} (izlenen {len(tracked_items)}, sayisal {anonymous_returned})"
        work_orders["transitionLog"] = _prepend_capped(
            work_orders["transitionLog"],
            _work_order_log_row(
                log_order,
                event_type="rolled_back",
                stamp=rollback_text,
                note=note,
            ),
        )
        if returned_to_inventory > 0:
            _set_summary(
                state,
                f"{active_order_id} geri alindi. {returned_to_inventory} adet depoya tasindi.",
                now=stamp,
            )
        else:
            _set_summary(
                state,
                f"{active_order_id} geri alindi ve yeniden kuyruga alindi.",
                now=stamp,
            )
        self.write_state(state)
        return {
            "state": state,
            "summary": state["lastEventSummary"],
            "order": order,
            "returned_to_inventory": returned_to_inventory,
            "tracked_items": len(tracked_items),
            "anonymous_returned": anonymous_returned,
        }

    @_state_locked
    def reset_work_orders(self, *, now: datetime | None = None) -> dict[str, Any]:
        stamp = now or datetime.now().astimezone()
        if stamp.tzinfo is None:
            stamp = stamp.astimezone()
        reset_text = _pseudo_iso_text(stamp)
        state = self.read_state()
        work_orders = _work_orders_state(state)
        previous_source = work_orders.get("source") if isinstance(work_orders.get("source"), dict) else {}
        reset_state = default_work_order_state()
        reset_state["toleranceMs"] = _duration_ms(
            _first_present(work_orders.get("toleranceMs"), work_orders.get("toleranceMinutes")),
            multiplier=60_000.0 if work_orders.get("toleranceMs") in (None, "") else 1.0,
        )
        reset_state["toleranceMinutes"] = _minutes_from_ms(reset_state["toleranceMs"])
        reset_state["source"]["folder"] = str(previous_source.get("folder") or "")
        work_orders.clear()
        work_orders.update(reset_state)
        state["recentItemIds"] = []
        state["qualityOverrideLog"] = []
        state["qualityOverrideResetAt"] = reset_text

        items = state.get("itemsById") if isinstance(state.get("itemsById"), dict) else {}
        cleared_item_count = 0
        for item in items.values():
            if not isinstance(item, dict):
                continue
            if item.get("completed_at"):
                item["inventory_backfill_disabled"] = True
            if not any(
                str(item.get(field) or "").strip()
                for field in ("work_order_id", "work_order_match_key", "inventory_match_key", "inventoryAction")
            ):
                continue
            _clear_item_work_order_context(item, updated_at=reset_text, inventory_action="")
            cleared_item_count += 1

        _set_summary(
            state,
            f"Is emirleri ve depo sifirlandi. {cleared_item_count} urun baglantisi temizlendi.",
            now=stamp,
        )
        self.write_state(state)
        return {
            "state": state,
            "summary": state["lastEventSummary"],
            "cleared_item_count": cleared_item_count,
        }

    @_state_locked
    def reset_runtime_counts(self, *, now: datetime | None = None) -> dict[str, Any]:
        stamp = now or datetime.now().astimezone()
        if stamp.tzinfo is None:
            stamp = stamp.astimezone()
        reset_text = _pseudo_iso_text(stamp)
        state = self.read_state()
        state["counts"] = {
            "total": 0,
            "good": 0,
            "rework": 0,
            "scrap": 0,
            "byColor": {
                "red": empty_color_counts(),
                "yellow": empty_color_counts(),
                "blue": empty_color_counts(),
            },
        }
        state["recentItemIds"] = []
        state["qualityOverrideLog"] = []
        state["qualityOverrideResetAt"] = reset_text
        state["earlyPickRejectLog"] = []
        state["trend"] = []
        items = state.get("itemsById") if isinstance(state.get("itemsById"), dict) else {}
        muted_completed_count = 0
        for item in items.values():
            if not isinstance(item, dict) or not item.get("completed_at"):
                continue
            item["count_in_oee"] = False
            muted_completed_count += 1
        _set_summary(
            state,
            f"OEE sayaclari sifirlandi. {muted_completed_count} tamamlanmis urun kalite listesi disina alindi.",
            now=stamp,
        )
        self.write_state(state)
        return {
            "state": state,
            "summary": state["lastEventSummary"],
            "muted_completed_count": muted_completed_count,
        }

    @_state_locked
    def remove_inventory_stock(self, match_key: str, quantity: Any = 1, *, now: datetime | None = None) -> dict[str, Any]:
        stamp = now or datetime.now().astimezone()
        if stamp.tzinfo is None:
            stamp = stamp.astimezone()
        update_text = _pseudo_iso_text(stamp)
        state = self.read_state()
        inventory = _work_order_inventory(state)
        normalized_match_key = str(match_key or "").strip()
        if not normalized_match_key:
            raise ValueError("INVALID_INVENTORY_MATCH_KEY")

        resolved_key = next(
            (
                key
                for key in inventory.keys()
                if str(key or "").strip().lower() == normalized_match_key.lower()
            ),
            normalized_match_key,
        )
        entry = inventory.get(resolved_key)
        if not isinstance(entry, dict):
            raise ValueError("INVENTORY_ENTRY_NOT_FOUND")

        current_qty = max(0, round(_numeric(entry.get("quantity"))))
        if current_qty <= 0:
            inventory.pop(resolved_key, None)
            raise ValueError("INVENTORY_ENTRY_EMPTY")

        requested_qty = max(1, round(_numeric(quantity)))
        removed_qty = min(current_qty, requested_qty)
        item_ids = _inventory_item_ids(entry)
        tracked_remove_count = min(len(item_ids), removed_qty)
        removed_item_ids = item_ids[-tracked_remove_count:] if tracked_remove_count > 0 else []
        if tracked_remove_count > 0:
            entry["itemIds"] = item_ids[:-tracked_remove_count]
        else:
            entry["itemIds"] = item_ids
        entry["quantity"] = max(0, current_qty - removed_qty)
        entry["lastUpdatedAt"] = update_text
        entry["lastSource"] = "manual_inventory_removed"

        items = state.get("itemsById") if isinstance(state.get("itemsById"), dict) else {}
        for item_id in removed_item_ids:
            item = items.get(item_id)
            if not isinstance(item, dict):
                continue
            item["inventory_match_key"] = ""
            item["inventoryAction"] = "manual_inventory_removed"
            item["inventory_backfill_disabled"] = True
            item["updated_at"] = update_text

        remaining_qty = max(0, round(_numeric(entry.get("quantity"))))
        label = str(entry.get("stockCode") or entry.get("productCode") or resolved_key or "stok")
        if remaining_qty <= 0:
            inventory.pop(resolved_key, None)
            summary = f"{label} deposundan {removed_qty} adet silindi. Satir temizlendi."
        else:
            summary = f"{label} deposundan {removed_qty} adet silindi. Kalan {remaining_qty} adet."
        _set_summary(state, summary, now=stamp)
        self.write_state(state)
        return {
            "state": state,
            "summary": state["lastEventSummary"],
            "match_key": resolved_key,
            "removed_qty": removed_qty,
            "remaining_qty": remaining_qty,
            "removed_item_ids": removed_item_ids,
        }

    @_state_locked
    def apply_mega_log(self, line: str, received_at: str) -> bool:
        parsed = parse_mega_event_from_log(line)
        if parsed is None:
            return False
        state = self.read_state()

        changed = False
        now = _parse_iso(received_at) or datetime.now().astimezone()
        item_id = str(parsed.get("item_id") or "").strip()
        measure_id = str(parsed.get("measure_id") or "").strip()
        item_key = item_id or (f"measure:{measure_id}" if measure_id else "")
        items = state["itemsById"] if isinstance(state.get("itemsById"), dict) else {}
        color = str(parsed.get("color") or "unknown")
        head_key = _head_item_key(state)

        if parsed["event_type"] == "measurement_decision" and item_key:
            item = _prepare_item_for_new_cycle(state, items, item_key, received_at=received_at)
            item.update(
                {
                    "item_id": item_id or item.get("item_id") or item_key,
                    "measure_id": measure_id or item.get("measure_id") or "",
                    "sensor_color": color,
                    "measured_at": received_at,
                    "detected_at": str(item.get("detected_at") or received_at),
                    "sensor_decision_source": str(parsed.get("decision_source") or item.get("sensor_decision_source") or ""),
                    "review_required": bool(parsed.get("review_required")),
                }
            )
            items[item_key] = item
            changed = True

        elif parsed["event_type"] == "queue_enq" and item_key:
            item = _prepare_item_for_new_cycle(state, items, item_key, received_at=received_at)
            item.update(
                {
                    "item_id": item_id or item.get("item_id") or item_key,
                    "measure_id": measure_id or item.get("measure_id") or "",
                    "sensor_color": color,
                    "vision_color": str(item.get("vision_color") or ""),
                    "final_color": str(item.get("final_color") or color),
                    "color": str(item.get("final_color") or color),
                    "decision_source": str(item.get("decision_source") or "SENSOR"),
                    "finalization_reason": str(item.get("finalization_reason") or "SENSOR_NO_VISION"),
                    "sensor_decision_source": str(parsed.get("decision_source") or item.get("sensor_decision_source") or ""),
                    "mismatch_flag": bool(item.get("mismatch_flag")),
                    "correlation_status": str(item.get("correlation_status") or ""),
                    "review_required": bool(parsed.get("review_required")),
                    "detected_at": str(item.get("detected_at") or item.get("measured_at") or received_at),
                    "queued_at": received_at,
                    "travel_ms": parsed.get("travel_ms"),
                    "travel_ms_initial": parsed.get("travel_ms"),
                    "queue_status": "waiting_travel",
                    "pick_started": False,
                    "pick_trigger_source": str(item.get("pick_trigger_source") or ""),
                    "early_pick_triggered": bool(item.get("early_pick_triggered")),
                    "late_vision_audit_flag": bool(item.get("late_vision_audit_flag")),
                    "count_in_oee": bool(item.get("count_in_oee")) or bool(state["shift"]["active"]),
                }
            )
            items[item_key] = item
            if item_key not in _queue_order(state):
                _queue_order(state).append(item_key)
            changed = True

        elif parsed["event_type"] == "arm_position_reached":
            resolved_key = item_key or head_key
            if not resolved_key:
                return False
            item = items.get(resolved_key, {})
            if item.get("pick_started"):
                return False
            trigger_source = str(parsed.get("trigger_source") or item.get("pick_trigger_source") or "TIMER").upper()
            item.update(
                {
                    "item_id": item_id or item.get("item_id") or resolved_key,
                    "measure_id": measure_id or item.get("measure_id") or "",
                    "pick_started": True,
                    "picked_at": received_at,
                    "queue_status": "picked",
                    "pick_trigger_source": trigger_source,
                }
            )
            if trigger_source == "EARLY" and not item.get("early_pick_accepted_at"):
                item["early_pick_accepted_at"] = received_at
                item["early_pick_triggered"] = True
                _vision_state(state)["metrics"]["earlyAcceptedCount"] = max(
                    0,
                    round(_numeric(_vision_state(state)["metrics"].get("earlyAcceptedCount"))),
                ) + 1
            items[resolved_key] = item
            changed = True

        elif parsed["event_type"] == "pick_command_rejected":
            resolved_key = item_key or head_key
            if not resolved_key:
                return False
            item = items.get(resolved_key, {})
            reject_reason = str(parsed.get("reject_reason") or "SAFETY_BLOCK").upper()
            item.update(
                {
                    "item_id": item_id or item.get("item_id") or resolved_key,
                    "measure_id": measure_id or item.get("measure_id") or "",
                    "last_reject_reason": reject_reason,
                    "last_reject_at": received_at,
                    "queue_status": "waiting_travel",
                }
            )
            if reject_reason == "HEAD_CHANGED":
                item["correlation_status"] = "DRIFTED"
            items[resolved_key] = item
            vision = _vision_state(state)
            vision["lastRejectReason"] = reject_reason
            vision["metrics"]["earlyRejectedCount"] = max(
                0,
                round(_numeric(vision["metrics"].get("earlyRejectedCount"))),
            ) + 1
            reject_log = state["earlyPickRejectLog"] if isinstance(state.get("earlyPickRejectLog"), list) else []
            reject_log.insert(
                0,
                {
                    "item_id": str(item.get("item_id") or resolved_key),
                    "measure_id": str(item.get("measure_id") or ""),
                    "reason": reject_reason,
                    "rejected_at": received_at,
                },
            )
            state["earlyPickRejectLog"] = reject_log[:20]
            changed = True

        elif parsed["event_type"] == "pick_released":
            resolved_key = item_key or head_key
            if not resolved_key or resolved_key not in items:
                return False
            item = items.get(resolved_key, {})
            if item.get("released_at") != received_at:
                item["released_at"] = received_at
                items[resolved_key] = item
                changed = True
            if _complete_runtime_item(
                state,
                items,
                resolved_key=resolved_key,
                item_id=item_id,
                measure_id=measure_id,
                color=color,
                parsed=parsed,
                received_at=received_at,
                now=now,
            ):
                changed = True

        elif parsed["event_type"] == "pick_return_started":
            resolved_key = item_key or head_key
            if not resolved_key or resolved_key not in items:
                return False
            items[resolved_key]["return_started_at"] = received_at
            changed = True

        elif parsed["event_type"] == "pick_return_reached":
            resolved_key = item_key or head_key
            if not resolved_key or resolved_key not in items:
                return False
            items[resolved_key]["return_reached_at"] = received_at
            changed = True

        elif parsed["event_type"] == "pickplace_return_done":
            resolved_key = item_key or head_key
            if not resolved_key or resolved_key not in items:
                return False
            items[resolved_key]["return_done_at"] = received_at
            changed = True

        elif parsed["event_type"] == "pickplace_done":
            resolved_key = item_key or head_key
            if not resolved_key:
                return False
            changed = _complete_runtime_item(
                state,
                items,
                resolved_key=resolved_key,
                item_id=item_id,
                measure_id=measure_id,
                color=color,
                parsed=parsed,
                received_at=received_at,
                now=now,
            )

        if changed:
            if state["shift"]["active"] and parsed["event_type"] in {"pick_released", "pickplace_done"}:
                _append_oee_trend_snapshot(state, now=now, reason=parsed["event_type"], force=True)
            state["itemsById"] = items
            self.write_state(state)
        return changed

    @_state_locked
    def apply_quality_override(self, item_id: str, classification: Any, *, now: datetime | None = None) -> dict[str, Any]:
        stamp = now or datetime.now().astimezone()
        if stamp.tzinfo is None:
            stamp = stamp.astimezone()
        state = self.read_state()
        normalized_item_id = str(item_id or "").strip()
        if not normalized_item_id:
            raise ValueError("INVALID_ITEM_ID")

        items = state["itemsById"] if isinstance(state.get("itemsById"), dict) else {}
        item_key = _resolve_item_lookup_key(items, normalized_item_id, completed_only=True)
        item = items.get(item_key)
        if not isinstance(item, dict):
            raise ValueError("ITEM_NOT_FOUND")
        if not item.get("completed_at"):
            raise ValueError("ITEM_NOT_COMPLETED")

        next_classification = _normalize_classification(classification)
        previous_classification = _normalize_classification(item.get("classification"))
        if previous_classification == next_classification:
            _set_summary(state, f"#{normalized_item_id} zaten {next_classification} durumunda.", now=stamp)
            self.write_state(state)
            return {
                "state": state,
                "item": item,
                "summary": state["lastEventSummary"],
                "override": None,
            }

        item["classification"] = next_classification
        item["updated_at"] = _pseudo_iso_text(stamp)
        item["override_applied_at"] = item["updated_at"]
        item["override_source"] = "MANUAL"
        inventory_sync_result = _sync_completed_item_inventory_eligibility(
            state,
            item,
            received_at=item["updated_at"],
            source="quality_override_inventory",
        )
        _recompute_item_counts(state)
        work_order_note = ""
        work_order_id = str(item.get("work_order_id") or "").strip()
        if work_order_id:
            order = _work_order_orders(state).get(work_order_id)
            if isinstance(order, dict):
                blocking_status = str(order.get("status") or "") in WORK_ORDER_BLOCKING_STATUSES
                previous_counts = _work_order_completion_counts_toward_fulfillment(previous_classification)
                next_counts = _work_order_completion_counts_toward_fulfillment(next_classification)
                fulfillment_delta = int(next_counts) - int(previous_counts)
                if blocking_status and fulfillment_delta != 0:
                    requirement = _find_work_order_requirement_by_match(
                        order,
                        str(item.get("work_order_match_key") or item.get("inventory_match_key") or ""),
                    )
                    inventory_delta = fulfillment_delta if str(item.get("inventoryAction") or "") == "consumed_for_work_order" else 0
                    if isinstance(requirement, dict):
                        requirement["completedQty"] = max(0, round(_numeric(requirement.get("completedQty"))) + fulfillment_delta)
                        if inventory_delta:
                            requirement["inventoryConsumedQty"] = max(0, round(_numeric(requirement.get("inventoryConsumedQty"))) + inventory_delta)
                        _sync_work_order_requirement(requirement)
                    else:
                        order["completedQty"] = max(0, round(_numeric(order.get("completedQty"))) + fulfillment_delta)
                        if inventory_delta:
                            order["inventoryConsumedQty"] = max(0, round(_numeric(order.get("inventoryConsumedQty"))) + inventory_delta)
                    _sync_work_order_row(order)
                    if fulfillment_delta < 0 and str(order.get("status") or "") == "pending_approval":
                        order["status"] = "active"
                        order["autoCompletedAt"] = ""
                        order["completedAt"] = ""
                        _work_orders_state(state)["activeOrderId"] = work_order_id
                        inventory_used = _consume_inventory_for_order(state, order, now=stamp, reason="quality_override_recovery")
                        if str(order.get("status") or "") == "pending_approval":
                            work_order_note = f" {work_order_id} yeniden otomatik tamamlandi ve operator onayi bekliyor."
                            if inventory_used > 0:
                                work_order_note = f" {work_order_id} kalite override sonrasi depodan {inventory_used} adet ile yeniden otomatik tamamlandi."
                        else:
                            work_order_note = f" {work_order_id} kalite override nedeniyle yeniden aktif oldu."
                            if inventory_used > 0:
                                work_order_note = f" {work_order_id} kalite override sonrasi depodan {inventory_used} adet kullanildi."
                    elif fulfillment_delta > 0 and str(order.get("status") or "") == "active":
                        auto_completed_at = str(item.get("completed_at") or item["updated_at"] or _pseudo_iso_text(stamp))
                        if _mark_work_order_pending_approval_if_ready(state, order, now=stamp, completed_at=auto_completed_at):
                            work_order_note = f" {work_order_id} yeniden otomatik tamamlandi ve operator onayi bekliyor."
                        else:
                            _persist_work_order_metrics(state, order, now=stamp)
                    else:
                        _persist_work_order_metrics(state, order, now=stamp)
                else:
                    _persist_work_order_metrics(state, order, now=stamp)
        override_row = {
            "item_id": normalized_item_id,
            "measure_id": str(item.get("measure_id") or ""),
            "previous_classification": previous_classification,
            "classification": next_classification,
            "applied_at": item["updated_at"],
            "color": str(item.get("color") or ""),
        }
        history = state["qualityOverrideLog"] if isinstance(state.get("qualityOverrideLog"), list) else []
        history.insert(0, override_row)
        state["qualityOverrideLog"] = history[:20]
        _set_summary(
            state,
            (
                f"#{normalized_item_id} kalite karari {previous_classification} -> {next_classification} olarak guncellendi."
                + (
                    " Hurda urun inventory listesinden cikarildi."
                    if inventory_sync_result == "removed_for_scrap"
                    else " Uygun oldugu icin inventory listesine alindi."
                    if inventory_sync_result == "added_to_inventory"
                    else ""
                )
                + work_order_note
            ),
            now=stamp,
        )
        if state["shift"]["active"]:
            _append_oee_trend_snapshot(state, now=stamp, reason="quality_override", force=True)
        self.write_state(state)
        return {
            "state": state,
            "item": item,
            "summary": state["lastEventSummary"],
            "override": override_row,
        }

    @_state_locked
    def apply_early_pick_request(self, item_id: str, sent_at: str) -> bool:
        state = self.read_state()
        items = state["itemsById"] if isinstance(state.get("itemsById"), dict) else {}
        item = items.get(str(item_id or "").strip())
        if not isinstance(item, dict):
            return False
        if item.get("early_pick_request_sent_at"):
            return False
        item["early_pick_request_sent_at"] = sent_at
        item["queue_status"] = "early_pick_requested"
        items[str(item_id or "").strip()] = item
        state["itemsById"] = items
        self.write_state(state)
        return True

    @_state_locked
    def apply_vision_status(self, payload: Any, received_at: str) -> bool:
        parsed = parse_vision_status(payload)
        if parsed is None:
            return False
        state = self.read_state()
        vision = _vision_state(state)
        vision["fps"] = max(0.0, _numeric(parsed.get("fps")))
        vision["lastStatusAt"] = received_at
        changed = _update_vision_health(
            state,
            now=_parse_iso(received_at) or datetime.now().astimezone(),
            heartbeat_timeout_sec=self.heartbeat_timeout_sec,
            degraded_fps=self.vision_degraded_fps,
            degraded_latency_ratio=self.vision_degraded_latency_ratio,
            decision_deadline_ms=self.vision_decision_deadline_ms,
            bad_window_threshold=self.vision_bad_window_threshold,
            recovery_window_threshold=self.vision_recovery_window_threshold,
        )
        self.write_state(state)
        return True

    @_state_locked
    def apply_vision_tracks(self, payload: Any, received_at: str) -> bool:
        parsed = parse_vision_tracks(payload)
        if parsed is None:
            return False
        state = self.read_state()
        vision = _vision_state(state)
        vision["lastTracksAt"] = received_at
        vision["activeTracks"] = int(parsed.get("active_tracks") or 0)
        vision["pendingTracks"] = int(parsed.get("pending_tracks") or 0)
        vision["totalCrossings"] = int(parsed.get("total_crossings") or 0)
        self.write_state(state)
        return True

    @_state_locked
    def apply_vision_heartbeat(self, payload: Any, received_at: str) -> bool:
        parsed = parse_vision_heartbeat(payload)
        if parsed is None:
            return False
        state = self.read_state()
        vision = _vision_state(state)
        vision["lastHeartbeatAt"] = str(parsed.get("timestamp") or received_at)
        changed = _update_vision_health(
            state,
            now=_parse_iso(received_at) or datetime.now().astimezone(),
            heartbeat_timeout_sec=self.heartbeat_timeout_sec,
            degraded_fps=self.vision_degraded_fps,
            degraded_latency_ratio=self.vision_degraded_latency_ratio,
            decision_deadline_ms=self.vision_decision_deadline_ms,
            bad_window_threshold=self.vision_bad_window_threshold,
            recovery_window_threshold=self.vision_recovery_window_threshold,
        )
        self.write_state(state)
        return True

    @_state_locked
    def apply_vision_event(self, payload: Any, received_at: str) -> dict[str, Any]:
        parsed = parse_vision_event(payload)
        if parsed is None:
            return {"changed": False, "publish_command": None, "item_id": "", "payload": payload}

        state = self.read_state()
        items = state["itemsById"] if isinstance(state.get("itemsById"), dict) else {}
        now = _parse_iso(received_at) or datetime.now().astimezone()
        vision = _vision_state(state)
        vision["lastEventAt"] = received_at
        vision["lastObservedAt"] = str(parsed.get("vision_observed_at") or "")
        vision["lastPublishedAt"] = str(parsed.get("vision_published_at") or parsed.get("vision_observed_at") or "")
        vision["lastReceivedAt"] = received_at

        observed_at = _parse_iso(str(parsed.get("vision_observed_at") or ""))
        if observed_at is not None:
            vision["eventLatencyMs"] = max(0, int((now - observed_at).total_seconds() * 1000))

        _update_vision_health(
            state,
            now=now,
            heartbeat_timeout_sec=self.heartbeat_timeout_sec,
            degraded_fps=self.vision_degraded_fps,
            degraded_latency_ratio=self.vision_degraded_latency_ratio,
            decision_deadline_ms=self.vision_decision_deadline_ms,
            bad_window_threshold=self.vision_bad_window_threshold,
            recovery_window_threshold=self.vision_recovery_window_threshold,
        )
        changed = True

        track_id = str(parsed.get("track_id") or "").strip()
        dedupe_key = f"{parsed['event_type']}:{track_id}" if track_id else ""
        if dedupe_key and dedupe_key in _processed_vision_keys(state):
            enriched = dict(parsed["raw"])
            enriched.update(
                {
                    "confidence": parsed.get("confidence", 0.0),
                    "confidence_tier": parsed.get("confidence_tier") or _vision_confidence_tier(parsed.get("confidence")),
                    "correlation_status": "MATCHED" if parsed.get("item_id") else "",
                    "observed_at": parsed.get("vision_observed_at"),
                    "published_at": parsed.get("vision_published_at"),
                    "received_at": received_at,
                    "duplicate_ignored": True,
                }
            )
            self.write_state(state)
            return {"changed": changed, "publish_command": None, "item_id": "", "payload": enriched}

        confidence_tier = str(parsed.get("confidence_tier") or _vision_confidence_tier(parsed.get("confidence")))
        head_key = _head_item_key(state)
        item = items.get(head_key) if head_key else None
        publish_command: str | None = None

        enriched = dict(parsed["raw"])
        enriched.update(
            {
                "confidence": parsed.get("confidence", 0.0),
                "confidence_tier": confidence_tier,
                "observed_at": parsed.get("vision_observed_at"),
                "published_at": parsed.get("vision_published_at"),
                "received_at": received_at,
                "duplicate_ignored": False,
            }
        )

        if parsed["event_type"] != "line_crossed":
            self.write_state(state)
            return {"changed": changed, "publish_command": None, "item_id": "", "payload": enriched}

        if not isinstance(item, dict):
            enriched["correlation_status"] = "DRIFTED"
            _remember_processed_vision_key(state, dedupe_key)
            changed = True
        else:
            remaining_ms = _remaining_travel_ms(item, now=now)
            is_late = bool(vision.get("eventLatencyMs") not in (None, "") and _numeric(vision.get("eventLatencyMs")) > self.vision_decision_deadline_ms)
            if item.get("pick_started") or remaining_ms <= 0:
                is_late = True
            fault_active = isinstance(state.get("activeFault"), dict)

            item.update(
                {
                    "vision_track_id": track_id,
                    "vision_confidence": parsed.get("confidence", 0.0),
                    "vision_observed_at": parsed.get("vision_observed_at"),
                    "vision_published_at": parsed.get("vision_published_at"),
                    "vision_received_at": received_at,
                    "queue_status": "in_pick_zone" if not item.get("pick_started") else str(item.get("queue_status") or ""),
                }
            )

            if fault_active:
                item["correlation_status"] = "FAULT_ACTIVE"
                item["finalization_reason"] = "SENSOR_FAULT_WINDOW"
            elif confidence_tier == "low":
                item["correlation_status"] = "IGNORED_LOW_CONF"
                item["finalization_reason"] = "SENSOR_LOW_CONF_VISION_IGNORED"
            elif is_late:
                item["correlation_status"] = "LATE"
                item["late_vision_audit_flag"] = True
                item["finalization_reason"] = "SENSOR_LATE_VISION"
                item["review_required"] = True
                vision["metrics"]["lateAuditCount"] = max(0, round(_numeric(vision["metrics"].get("lateAuditCount")))) + 1
            elif confidence_tier == "medium":
                item["correlation_status"] = "AMBIGUOUS"
                item["review_required"] = True
            else:
                sensor_color = str(item.get("sensor_color") or "")
                vision_color = str(parsed.get("color") or "")
                item["vision_color"] = vision_color
                item["final_color"] = vision_color
                item["color"] = vision_color
                item["decision_source"] = "VISION"
                item["queue_status"] = "vision_confirmed"
                item["correlation_status"] = "MATCHED"
                item["decision_applied_at"] = received_at
                if sensor_color and sensor_color != vision_color:
                    was_mismatch = bool(item.get("mismatch_flag"))
                    item["mismatch_flag"] = True
                    item["finalization_reason"] = "VISION_CORRECTED_MISMATCH"
                    if not was_mismatch:
                        vision["metrics"]["mismatchCount"] = max(0, round(_numeric(vision["metrics"].get("mismatchCount")))) + 1
                else:
                    item["finalization_reason"] = "VISION_HIGH_CONF"

                if (
                    str(vision.get("healthState") or "") == "online"
                    and remaining_ms >= self.min_remaining_travel_ms_for_early_pick
                    and not item.get("early_pick_request_sent_at")
                    and not item.get("pick_started")
                ):
                    publish_command = f"epick {item.get('item_id') or head_key}"

            items[head_key] = item
            enriched.update(
                {
                    "item_id": item.get("item_id") or head_key,
                    "measure_id": item.get("measure_id") or "",
                    "correlation_status": item.get("correlation_status") or "",
                    "late_vision_audit_flag": bool(item.get("late_vision_audit_flag")),
                    "decision_applied": bool(item.get("decision_source") == "VISION" and item.get("correlation_status") == "MATCHED"),
                    "review_required": bool(item.get("review_required")),
                }
            )
            _append_recent_id(state, head_key)
            _remember_processed_vision_key(state, dedupe_key)
            changed = True

        state["itemsById"] = items
        self.write_state(state)
        return {
            "changed": changed,
            "publish_command": publish_command,
            "item_id": str((items.get(head_key) or {}).get("item_id") or head_key or ""),
            "payload": enriched,
        }

    @_state_locked
    def apply_tablet_fault_log(self, line: str, received_at: str) -> bool:
        parsed = parse_tablet_fault_line(line)
        if parsed is None:
            return False
        state = self.read_state()
        if not state["shift"]["active"]:
            return False

        now = _parse_iso(received_at) or datetime.now().astimezone()
        status = str(parsed.get("status") or "").strip().upper()
        if status == "BASLADI":
            if isinstance(state.get("activeFault"), dict):
                _close_active_fault(state, ended_at=received_at)
            state["activeFault"] = {
                "faultId": str(int(now.timestamp() * 1000)),
                "category": "BILINMIYOR",
                "reason": str(parsed.get("reason") or "Bilinmiyor"),
                "startedAt": _merge_clock_with_stamp(parsed.get("started_at_text"), received_at),
                "durationMs": _duration_ms(
                    _first_present(parsed.get("duration_ms"), parsed.get("duration_min")),
                    multiplier=60_000.0 if parsed.get("duration_ms") in (None, "") else 1.0,
                ),
                "durationMin": _minutes_from_ms(
                    _duration_ms(
                        _first_present(parsed.get("duration_ms"), parsed.get("duration_min")),
                        multiplier=60_000.0 if parsed.get("duration_ms") in (None, "") else 1.0,
                    ),
                    precision=3,
                ),
            }
            _set_summary(state, f"Aktif fault: {state['activeFault']['reason']}", now=now)
            _append_oee_trend_snapshot(state, now=now, reason="fault_started", force=True)
            self.write_state(state)
            return True

        if status == "BITTI":
            ended_at = _merge_clock_with_stamp(parsed.get("ended_at_text"), received_at)
            if isinstance(state.get("activeFault"), dict):
                _close_active_fault(state, ended_at=ended_at)
            _set_summary(state, f"Fault kapandi: {parsed.get('reason') or 'Bilinmiyor'}", now=now)
            _append_oee_trend_snapshot(state, now=now, reason="fault_cleared", force=True)
            self.write_state(state)
            return True
        return False

    @_state_locked
    def tick(self, *, now: datetime | None = None) -> bool:
        state = self.read_state()
        stamp = now or datetime.now().astimezone()
        changed = _update_vision_health(
            state,
            now=stamp,
            heartbeat_timeout_sec=self.heartbeat_timeout_sec,
            degraded_fps=self.vision_degraded_fps,
            degraded_latency_ratio=self.vision_degraded_latency_ratio,
            decision_deadline_ms=self.vision_decision_deadline_ms,
            bad_window_threshold=self.vision_bad_window_threshold,
            recovery_window_threshold=self.vision_recovery_window_threshold,
        )
        if not state["shift"]["active"]:
            if changed:
                state["lastUpdatedAt"] = _pseudo_iso_text(stamp)
                self.write_state(state)
            return changed

        snapshot_logged = _append_oee_trend_snapshot(state, now=stamp, reason="periodic_30s", force=False)
        if changed or snapshot_logged:
            if not snapshot_logged:
                state["lastUpdatedAt"] = _pseudo_iso_text(stamp)
            self.write_state(state)
        return changed or snapshot_logged

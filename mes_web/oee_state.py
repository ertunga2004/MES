from __future__ import annotations

import contextlib
import json
import os
import threading
import time
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

WORK_ORDER_STATUSES = {"queued", "active", "completed"}


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


class WorkOrderTransitionReasonRequired(ValueError):
    def __init__(
        self,
        *,
        order_id: str,
        previous_order_id: str,
        elapsed_minutes: float,
        tolerance_minutes: float,
    ) -> None:
        super().__init__("WORK_ORDER_REASON_REQUIRED")
        self.order_id = order_id
        self.previous_order_id = previous_order_id
        self.elapsed_minutes = elapsed_minutes
        self.tolerance_minutes = tolerance_minutes


def default_runtime_state() -> dict[str, Any]:
    return {
        "version": 4,
        "shiftSelected": "SHIFT-A",
        "performanceMode": "TARGET",
        "targetQty": 14,
        "idealCycleSec": 10.0,
        "plannedStopMin": 0.0,
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
            "idealCycleSec": 10.0,
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
        "processedVisionEventKeys": [],
        "activeFault": None,
        "faultHistory": [],
        "unplannedDowntimeMs": 0,
        "trend": [],
        "qualityOverrideLog": [],
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


def _pseudo_iso_text(value: datetime) -> str:
    base = value if value.tzinfo is not None else value.astimezone()
    return base.astimezone().isoformat(timespec="milliseconds")


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


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
    shift["idealCycleSec"] = state["idealCycleSec"]
    shift["plannedStopMin"] = state["plannedStopMin"]


def _text_or_default(value: Any, default: str = "") -> str:
    return str(value or "").strip() or default


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "evet"}


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
    color = _normalize_order_color(
        entry.get("color"),
        entry.get("productColor"),
        entry.get("stockCode"),
        entry.get("stockName"),
    )
    resolved_match_key = str(entry.get("matchKey") or "").strip() or match_key or color or str(entry.get("productCode") or entry.get("stockCode") or "").strip()
    return {
        "matchKey": resolved_match_key,
        "productCode": _text_or_default(entry.get("productCode") or entry.get("stockCode"), resolved_match_key),
        "stockCode": _text_or_default(entry.get("stockCode") or entry.get("productCode"), resolved_match_key),
        "stockName": _text_or_default(entry.get("stockName"), resolved_match_key or color or "Urun"),
        "color": color,
        "quantity": max(0, round(_numeric(entry.get("quantity") or entry.get("availableQty") or 0))),
        "lastUpdatedAt": _text_or_default(entry.get("lastUpdatedAt")),
        "lastSource": _text_or_default(entry.get("lastSource")),
    }


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
        entry.get("stock_code") or entry.get("stockCode") or entry.get("stok_kodu"),
        entry.get("stock_name") or entry.get("stockName") or entry.get("stok_adi"),
        current.get("color"),
        current.get("stockCode"),
        current.get("stockName"),
    )
    product_code = _text_or_default(
        entry.get("product_code")
        or entry.get("productCode")
        or entry.get("stock_code")
        or entry.get("stockCode")
        or current.get("productCode"),
        fallback_product_code or fallback_stock_code or fallback_line_id,
    )
    stock_code = _text_or_default(
        entry.get("stock_code")
        or entry.get("stockCode")
        or current.get("stockCode"),
        fallback_stock_code or product_code or fallback_line_id,
    )
    stock_name = _text_or_default(
        entry.get("stock_name")
        or entry.get("stockName")
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
        "quantity": max(0, round(_numeric(entry.get("qty") or entry.get("quantity") or entry.get("miktar") or current.get("quantity") or 0))),
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
                "productCode": entry.get("product_code") or entry.get("productCode") or current.get("productCode"),
                "stockCode": entry.get("stock_code") or entry.get("stockCode") or current.get("stockCode"),
                "stockName": entry.get("stock_name") or entry.get("stockName") or current.get("stockName"),
                "color": entry.get("product_color") or entry.get("productColor") or entry.get("color") or current.get("productColor"),
                "matchKey": entry.get("matchKey") or current.get("matchKey"),
                "qty": entry.get("qty") or entry.get("quantity") or current.get("quantity"),
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

    fallback_product_code = _text_or_default(entry.get("product_code") or entry.get("productCode") or current.get("productCode"))
    fallback_stock_code = _text_or_default(entry.get("stock_code") or entry.get("stockCode") or current.get("stockCode"))
    fallback_stock_name = _text_or_default(entry.get("stock_name") or entry.get("stockName") or current.get("stockName"))
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
        or current.get("orderId")
    )
    color = _normalize_order_color(
        entry.get("product_color")
        or entry.get("productColor")
        or entry.get("color")
        or entry.get("renk"),
        entry.get("stock_code") or entry.get("stockCode") or entry.get("stok_kodu"),
        entry.get("stock_name") or entry.get("stockName") or entry.get("stok_adi") or entry.get("stokAdı"),
        current.get("productColor"),
    )
    product_code = _text_or_default(
        entry.get("product_code")
        or entry.get("productCode")
        or entry.get("stock_code")
        or entry.get("stockCode")
        or entry.get("stok_kodu")
        or entry.get("stokKodu")
        or current.get("productCode")
    )
    stock_code = _text_or_default(
        entry.get("stock_code")
        or entry.get("stockCode")
        or entry.get("stok_kodu")
        or entry.get("stokKodu")
        or current.get("stockCode")
        or product_code
    )
    stock_name = _text_or_default(
        entry.get("stock_name")
        or entry.get("stockName")
        or entry.get("stok_adi")
        or entry.get("stokAdı")
        or current.get("stockName"),
        stock_code or order_id,
    )
    status = _text_or_default(entry.get("status"), str(current.get("status") or "queued")).lower()
    if status not in WORK_ORDER_STATUSES:
        status = "queued"
    requirements = _normalize_work_order_requirements(entry, current)
    order = {
        "orderId": order_id,
        "erpType": _text_or_default(entry.get("erp_type") or entry.get("erpType") or entry.get("tip") or current.get("erpType"), "Is Emirleri"),
        "date": _text_or_default(entry.get("date") or entry.get("tarih") or current.get("date")),
        "systemNo": _text_or_default(entry.get("system_no") or entry.get("systemNo") or entry.get("sistem_no") or entry.get("sistemNo") or current.get("systemNo")),
        "sequenceNo": max(0, round(_numeric(entry.get("sequence_no") or entry.get("sequenceNo") or entry.get("sira") or entry.get("sıra") or current.get("sequenceNo")))),
        "locked": _boolish(entry.get("locked") if entry.get("locked") is not None else entry.get("kilit") if entry.get("kilit") is not None else current.get("locked")),
        "stockType": _text_or_default(entry.get("stock_type") or entry.get("stockType") or entry.get("stok_servis") or entry.get("stokServis") or current.get("stockType")),
        "stockCode": stock_code,
        "stockName": stock_name,
        "unit": _text_or_default(entry.get("unit") or entry.get("birim") or current.get("unit")),
        "methodCode": _text_or_default(entry.get("method_code") or entry.get("methodCode") or entry.get("metod_kodu") or entry.get("metodKodu") or current.get("methodCode")),
        "quantity": 0,
        "projectCode": _text_or_default(entry.get("project_code") or entry.get("projectCode") or entry.get("proje") or current.get("projectCode")),
        "description": _text_or_default(entry.get("description") or entry.get("aciklama") or entry.get("açıklama") or current.get("description")),
        "workCenterCode": _text_or_default(entry.get("work_center_code") or entry.get("workCenterCode") or entry.get("is_merkezi") or entry.get("iş_merkezi") or current.get("workCenterCode")),
        "operationCode": _text_or_default(entry.get("operation_code") or entry.get("operationCode") or entry.get("operasyon") or current.get("operationCode")),
        "setupTimeSec": max(0.0, _numeric(entry.get("setup_time_sec") or entry.get("setupTimeSec") or entry.get("hazirlik_suresi_sec") or entry.get("hazırlık_süresi_sn") or current.get("setupTimeSec"))),
        "workerCount": max(0, round(_numeric(entry.get("worker_count") or entry.get("workerCount") or entry.get("isci_sayisi") or entry.get("işçi_sayısı") or current.get("workerCount")))),
        "cycleTimeSec": max(0.0, _numeric(entry.get("cycle_time_sec") or entry.get("cycleTimeSec") or entry.get("sure_sec") or entry.get("süre_saniye") or current.get("cycleTimeSec"))),
        "shiftCode": _text_or_default(entry.get("shift_code") or entry.get("shiftCode") or entry.get("vardiya") or current.get("shiftCode")),
        "productCode": product_code or stock_code or order_id,
        "productColor": color,
        "matchKey": _text_or_default(entry.get("matchKey") or current.get("matchKey"), color or product_code or stock_code or order_id),
        "status": status,
        "queuedAt": _text_or_default(entry.get("queuedAt") or current.get("queuedAt"), queued_at),
        "startedAt": _text_or_default(entry.get("startedAt") or current.get("startedAt")),
        "completedAt": _text_or_default(entry.get("completedAt") or current.get("completedAt")),
        "startedBy": _text_or_default(entry.get("startedBy") or current.get("startedBy")),
        "startedByName": _text_or_default(entry.get("startedByName") or current.get("startedByName")),
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


def ensure_runtime_state_shape(payload: Any) -> dict[str, Any]:
    candidate = payload if isinstance(payload, dict) else {}
    base = default_runtime_state()

    selected = str(candidate.get("shiftSelected") or base["shiftSelected"]).upper()
    base["shiftSelected"] = selected if selected in SHIFT_PRESETS else base["shiftSelected"]

    performance_mode = str(candidate.get("performanceMode") or base["performanceMode"]).upper()
    base["performanceMode"] = "IDEAL_CYCLE" if performance_mode == "IDEAL_CYCLE" else "TARGET"
    base["version"] = int(candidate.get("version") or base["version"])
    base["targetQty"] = max(0, round(_numeric(candidate.get("targetQty"))))
    base["idealCycleSec"] = max(0.0, _numeric(candidate.get("idealCycleSec")))
    base["plannedStopMin"] = max(0.0, _numeric(candidate.get("plannedStopMin")))

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
    base["shift"]["targetQty"] = max(0, round(_numeric(base["shift"].get("targetQty"))))
    base["shift"]["idealCycleSec"] = max(0.0, _numeric(base["shift"].get("idealCycleSec")))
    base["shift"]["plannedStopMin"] = max(0.0, _numeric(base["shift"].get("plannedStopMin")))

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
    base["workOrders"]["toleranceMinutes"] = max(0.0, _numeric(work_orders.get("toleranceMinutes") or base["workOrders"]["toleranceMinutes"]))
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
        if normalized["status"] == "completed" and not normalized["completedAt"]:
            normalized["completedAt"] = normalized["lastAllocationAt"] or normalized["startedAt"]
        if normalized["status"] == "active" and not normalized["startedAt"]:
            normalized["status"] = "queued"
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
    if active_order_id not in normalized_orders or normalized_orders.get(active_order_id, {}).get("status") != "active":
        active_order_id = ""
        for order_id in sequence:
            if normalized_orders.get(order_id, {}).get("status") == "active":
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
    base["workOrders"]["transitionLog"] = work_orders.get("transitionLog") if isinstance(work_orders.get("transitionLog"), list) else []
    base["workOrders"]["completionLog"] = work_orders.get("completionLog") if isinstance(work_orders.get("completionLog"), list) else []
    source = work_orders.get("source") if isinstance(work_orders.get("source"), dict) else {}
    base["workOrders"]["source"] = {
        "folder": str(source.get("folder") or ""),
        "file": str(source.get("file") or ""),
        "loadedAt": str(source.get("loadedAt") or ""),
    }
    base["processedVisionEventKeys"] = candidate.get("processedVisionEventKeys") if isinstance(candidate.get("processedVisionEventKeys"), list) else []
    base["activeFault"] = candidate.get("activeFault") if isinstance(candidate.get("activeFault"), dict) else None
    base["faultHistory"] = candidate.get("faultHistory") if isinstance(candidate.get("faultHistory"), list) else []
    base["unplannedDowntimeMs"] = max(0, round(_numeric(candidate.get("unplannedDowntimeMs"))))
    base["trend"] = candidate.get("trend") if isinstance(candidate.get("trend"), list) else []
    base["qualityOverrideLog"] = candidate.get("qualityOverrideLog") if isinstance(candidate.get("qualityOverrideLog"), list) else []
    base["earlyPickRejectLog"] = candidate.get("earlyPickRejectLog") if isinstance(candidate.get("earlyPickRejectLog"), list) else []
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
    state["unplannedDowntimeMs"] = max(0, round(_numeric(state.get("unplannedDowntimeMs")))) + duration_ms
    history = state["faultHistory"] if isinstance(state.get("faultHistory"), list) else []
    history.insert(
        0,
        {
            "faultId": str(active_fault.get("faultId") or ""),
            "category": str(active_fault.get("category") or "BILINMIYOR"),
            "reason": str(active_fault.get("reason") or "Bilinmiyor"),
            "startedAt": started_at,
            "endedAt": ended_at,
            "durationMs": duration_ms,
        },
    )
    state["faultHistory"] = history[:20]
    state["activeFault"] = None


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
    work_orders["toleranceMinutes"] = max(0.0, _numeric(work_orders.get("toleranceMinutes") or 0.0))
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
    order["availability"] = round(snapshot["availability"] * 100.0, 1)
    order["performance"] = round(snapshot["performance"] * 100.0, 1)
    order["quality"] = round(snapshot["quality"] * 100.0, 1)
    order["oee"] = round(snapshot["oee"] * 100.0, 1)
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
    return entry


def _complete_work_order_if_ready(state: dict[str, Any], order: dict[str, Any], *, now: datetime, completed_at: str) -> bool:
    _sync_work_order_row(order)
    if order.get("status") != "active":
        return False
    if max(0, round(_numeric(order.get("remainingQty")))) > 0:
        return False
    stamp = completed_at or _pseudo_iso_text(now)
    order["status"] = "completed"
    order["completedAt"] = stamp
    work_orders = _work_orders_state(state)
    if work_orders.get("activeOrderId") == order.get("orderId"):
        work_orders["activeOrderId"] = ""
    work_orders["lastCompletedOrderId"] = str(order.get("orderId") or "")
    work_orders["lastCompletedAt"] = stamp
    metrics = _persist_work_order_metrics(state, order, now=now)
    work_orders["completionLog"] = _prepend_capped(
        work_orders["completionLog"],
        _work_order_log_row(
            order,
            event_type="completed",
            stamp=stamp,
            note=f"Is emri sistem tarafindan kapatildi. OEE={round(metrics['oee'] * 100.0, 1)}%",
        ),
    )
    _set_summary(
        state,
        f"{order.get('orderId') or 'Is emri'} kapatildi. {order.get('completedQty')}/{order.get('quantity')} tamamlandi.",
        now=now,
    )
    return True


def _consume_inventory_for_order(state: dict[str, Any], order: dict[str, Any], *, now: datetime, reason: str = "inventory") -> int:
    inventory = _work_order_inventory(state)
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
        entry["quantity"] = max(0, round(_numeric(entry.get("quantity"))) - take_qty)
        entry["lastUpdatedAt"] = _pseudo_iso_text(now)
        entry["lastSource"] = "consumed_for_work_order"
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
    _complete_work_order_if_ready(state, order, now=now, completed_at=str(order.get("lastAllocationAt") or _pseudo_iso_text(now)))
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

    matching_requirement = _find_matching_requirement(active_order, item_color) if isinstance(active_order, dict) else None
    if isinstance(active_order, dict) and isinstance(matching_requirement, dict):
        matching_requirement["productionQty"] = max(0, round(_numeric(matching_requirement.get("productionQty")))) + 1
        matching_requirement["completedQty"] = max(0, round(_numeric(matching_requirement.get("completedQty")))) + 1
        active_order["lastAllocationAt"] = received_at
        _sync_work_order_row(active_order)
        item["work_order_id"] = str(active_order.get("orderId") or "")
        item["work_order_match_key"] = _work_order_requirement_match_key(matching_requirement)
        item["inventoryAction"] = "work_order"
        if not _complete_work_order_if_ready(state, active_order, now=now, completed_at=received_at):
            _set_summary(
                state,
                f"#{item_id} aktif {active_order.get('orderId')} is emrine {item_color} olarak yazildi. Kalan {active_order.get('remainingQty')} adet.",
                now=now,
            )
        return

    match_key = item_color or str(item.get("final_color") or item.get("color") or resolved_key)
    inventory_entry = _ensure_inventory_entry(
        inventory,
        match_key,
        product_code=match_key.upper(),
        stock_code=match_key.upper(),
        stock_name=(item_color or match_key).upper(),
        color=item_color,
    )
    inventory_entry["quantity"] = max(0, round(_numeric(inventory_entry.get("quantity")))) + 1
    inventory_entry["lastUpdatedAt"] = received_at
    inventory_entry["lastSource"] = "off_order_completion"
    item["inventoryAction"] = "stored"
    item["inventory_match_key"] = match_key
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
    stamp = now or datetime.now().astimezone()
    counts = state.get("counts") if isinstance(state.get("counts"), dict) else {}
    shift = state.get("shift") if isinstance(state.get("shift"), dict) else {}
    total = max(0, round(_numeric(counts.get("total"))))
    good = max(0, round(_numeric(counts.get("good"))))
    rework = max(0, round(_numeric(counts.get("rework"))))
    scrap = max(0, round(_numeric(counts.get("scrap"))))

    shift_active = bool(shift.get("active") and shift.get("startedAt"))
    started_at = _parse_iso(str(shift.get("startedAt") or ""))
    plan_start = _parse_iso(str(shift.get("planStart") or ""))
    plan_end = _parse_iso(str(shift.get("planEnd") or ""))
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

    active_fault = state.get("activeFault") if isinstance(state.get("activeFault"), dict) else None
    active_fault_started = _parse_iso(str(active_fault.get("startedAt") or "")) if active_fault else None
    active_fault_ms = 0
    if shift_active and active_fault_started is not None:
        active_fault_ms = max(0, int((stamp - active_fault_started).total_seconds() * 1000))

    planned_stop_total_ms = min(
        max(0, round(_numeric(shift.get("plannedStopMin") or state.get("plannedStopMin")) * 60_000.0)),
        shift_window_total_ms if shift_window_total_ms > 0 else max(0, elapsed_ms),
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
    target_qty = max(0, round(_numeric(shift.get("targetQty") or state.get("targetQty"))))
    ideal_cycle_sec = max(0.0, _numeric(shift.get("idealCycleSec") or state.get("idealCycleSec")))

    if performance_mode == "IDEAL_CYCLE" and ideal_cycle_sec > 0:
        expected = (runtime_ms / (ideal_cycle_sec * 1000.0)) if runtime_ms > 0 else 0.0
        performance = (total / expected) if expected > 0 else 0.0
        target_text = f"{ideal_cycle_sec:.1f} sn cycle / beklenen {expected:.1f}"
    elif target_qty > 0 and planned_production_total_ms > 0:
        expected = float(target_qty) * (runtime_ms / planned_production_total_ms) if runtime_ms > 0 else 0.0
        performance = (total / expected) if expected > 0 else 0.0
        target_text = f"{target_qty} adet hedef / beklenen {expected:.1f}"
    elif target_qty > 0:
        expected = float(target_qty)
        performance = 0.0
        target_text = f"{target_qty} adet hedef"

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
    ideal_cycle_sec = max(0.0, _numeric(order.get("cycleTimeSec") or state.get("idealCycleSec") or 10.0))
    if ideal_cycle_sec <= 0:
        ideal_cycle_sec = 10.0
    planned_duration_ms = int(target_qty * ideal_cycle_sec * 1000.0)
    started_at = _parse_iso(str(order.get("startedAt") or ""))
    completed_at = _parse_iso(str(order.get("completedAt") or ""))
    end_at = completed_at or stamp
    elapsed_ms = int((end_at - started_at).total_seconds() * 1000) if started_at is not None and end_at >= started_at else 0
    unplanned_ms = _work_order_fault_ms(state, start_at=started_at, end_at=end_at) if started_at is not None and elapsed_ms > 0 else 0
    runtime_ms = max(0, elapsed_ms - unplanned_ms)
    availability = (runtime_ms / planned_duration_ms) if planned_duration_ms > 0 else 0.0
    availability = max(0.0, min(1.0, availability))
    performance = ((production_qty * ideal_cycle_sec * 1000.0) / runtime_ms) if runtime_ms > 0 else 0.0
    performance = max(0.0, min(1.0, performance))
    quality = (good / total) if total > 0 else 1.0
    quality = max(0.0, min(1.0, quality))
    oee = availability * performance * quality
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
            f"|PLANLI_DURUS_DK:{float(shift['plannedStopMin']):.1f}"
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
            "set_planned_stop_min",
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
            recent_log = f"SYSTEM|OEE|SET_PERFORMANCE_MODE|{state['performanceMode']}"

        elif normalized_action == "set_target_qty":
            state["targetQty"] = max(0, round(_numeric(value)))
            _touch_shift_config(state)
            _set_summary(state, f"Hedef {state['targetQty']} adet olarak guncellendi.", now=stamp)
            recent_log = f"SYSTEM|OEE|SET_TARGET_QTY|{state['targetQty']}"

        elif normalized_action == "set_ideal_cycle_sec":
            state["idealCycleSec"] = max(0.0, _numeric(value))
            _touch_shift_config(state)
            _set_summary(state, f"Ideal cycle {state['idealCycleSec']:.1f} sn olarak guncellendi.", now=stamp)
            recent_log = f"SYSTEM|OEE|SET_IDEAL_CYCLE_SEC|{state['idealCycleSec']:.1f}"

        elif normalized_action == "set_planned_stop_min":
            state["plannedStopMin"] = max(0.0, _numeric(value))
            _touch_shift_config(state)
            _set_summary(state, f"Planli durus rezervi {state['plannedStopMin']:.1f} dk olarak guncellendi.", now=stamp)
            recent_log = f"SYSTEM|OEE|SET_PLANNED_STOP_MIN|{state['plannedStopMin']:.1f}"

        elif normalized_action == "shift_start":
            if state["shift"]["active"]:
                _set_summary(state, "Aktif vardiya bitmeden yeni vardiya baslatilamadi.", now=stamp)
                recent_log = "SYSTEM|OEE|SHIFT_START|REJECTED"
            else:
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
                    "idealCycleSec": state["idealCycleSec"],
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
                state["trend"] = []
                state["qualityOverrideLog"] = []
                state["earlyPickRejectLog"] = []
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
                system_line = _system_log_line("START", state, now=stamp)
                recent_log = system_line

        elif normalized_action == "shift_stop":
            if not state["shift"]["active"]:
                _set_summary(state, "Bitirilecek aktif vardiya yok.", now=stamp)
                recent_log = "SYSTEM|OEE|SHIFT_STOP|REJECTED"
            else:
                if isinstance(state.get("activeFault"), dict):
                    _close_active_fault(state, ended_at=_pseudo_iso_text(stamp))
                system_line = _system_log_line("STOP", state, now=stamp)
                state["shift"]["active"] = False
                state["shift"]["endedAt"] = _pseudo_iso_text(stamp)
                _set_summary(state, f"{state['shift']['code']} kapatildi. Vardiya ozeti kilitlendi.", now=stamp)
                recent_log = system_line

        self.write_state(state)
        return {
            "state": state,
            "summary": state["lastEventSummary"],
            "recent_log": recent_log,
            "system_line": system_line,
        }

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
        work_orders["toleranceMinutes"] = max(0.0, _numeric(minutes))
        _set_summary(state, f"Is emirleri arasi tolerans {work_orders['toleranceMinutes']:.1f} dk olarak ayarlandi.", now=stamp)
        self.write_state(state)
        return {
            "state": state,
            "summary": state["lastEventSummary"],
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
        tolerance_minutes = max(0.0, _numeric(work_orders.get("toleranceMinutes")))
        last_completed_order_id = str(work_orders.get("lastCompletedOrderId") or "").strip()
        last_completed_at = _parse_iso(str(work_orders.get("lastCompletedAt") or ""))
        cleaned_reason = str(transition_reason or "").strip()
        if last_completed_order_id and last_completed_at is not None and tolerance_minutes > 0:
            elapsed_minutes = max(0.0, (start_dt - last_completed_at).total_seconds() / 60.0)
            if elapsed_minutes > tolerance_minutes and not cleaned_reason:
                raise WorkOrderTransitionReasonRequired(
                    order_id=normalized_order_id,
                    previous_order_id=last_completed_order_id,
                    elapsed_minutes=elapsed_minutes,
                    tolerance_minutes=tolerance_minutes,
                )

        order["status"] = "active"
        order["startedAt"] = start_text
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
        if str(order.get("status") or "") == "completed":
            _set_summary(
                state,
                f"{normalized_order_id} baslatildi ve depodaki stok ile kapatildi.",
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
            item = items.get(item_key, {})
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
            item = items.get(item_key, {})
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
            state["itemsById"] = items
            self.write_state(state)
        return changed

    @_state_locked
    def apply_quality_override(self, item_id: str, classification: Any, *, now: datetime | None = None) -> dict[str, Any]:
        stamp = now or datetime.now().astimezone()
        state = self.read_state()
        normalized_item_id = str(item_id or "").strip()
        if not normalized_item_id:
            raise ValueError("INVALID_ITEM_ID")

        items = state["itemsById"] if isinstance(state.get("itemsById"), dict) else {}
        item = items.get(normalized_item_id)
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
        _recompute_item_counts(state)
        work_order_id = str(item.get("work_order_id") or "").strip()
        if work_order_id:
            order = _work_order_orders(state).get(work_order_id)
            if isinstance(order, dict):
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
        _set_summary(state, f"#{normalized_item_id} kalite karari {previous_classification} -> {next_classification} olarak guncellendi.", now=stamp)
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

            if confidence_tier == "low":
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
                "durationMin": max(0.0, _numeric(parsed.get("duration_min"))),
            }
            _set_summary(state, f"Aktif fault: {state['activeFault']['reason']}", now=now)
            self.write_state(state)
            return True

        if status == "BITTI":
            ended_at = _merge_clock_with_stamp(parsed.get("ended_at_text"), received_at)
            if isinstance(state.get("activeFault"), dict):
                _close_active_fault(state, ended_at=ended_at)
            _set_summary(state, f"Fault kapandi: {parsed.get('reason') or 'Bilinmiyor'}", now=now)
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

        last_logged = _parse_iso(str(state.get("lastSnapshotLoggedAt") or ""))
        if last_logged is not None and (stamp - last_logged).total_seconds() < 5:
            if changed:
                state["lastUpdatedAt"] = _pseudo_iso_text(stamp)
                self.write_state(state)
            return changed

        snapshot = build_live_snapshot(state, now=stamp)
        trend = state["trend"] if isinstance(state.get("trend"), list) else []
        trend.append(
            {
                "time": _pseudo_iso_text(stamp),
                "oee": round(snapshot["oee"] * 100.0, 1),
                "availability": round(snapshot["availability"] * 100.0, 1),
                "performance": round(snapshot["performance"] * 100.0, 1),
                "quality": round(snapshot["quality"] * 100.0, 1),
                "loss": round(snapshot["lossPct"], 1),
            }
        )
        state["trend"] = trend[-20:]
        state["lastSnapshotLoggedAt"] = _pseudo_iso_text(stamp)
        state["lastUpdatedAt"] = _pseudo_iso_text(stamp)
        self.write_state(state)
        return True

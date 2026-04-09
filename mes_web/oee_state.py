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


def default_runtime_state() -> dict[str, Any]:
    return {
        "version": 3,
        "shiftSelected": "SHIFT-A",
        "performanceMode": "TARGET",
        "targetQty": 0,
        "idealCycleSec": 0.0,
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
            "targetQty": 0,
            "idealCycleSec": 0.0,
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
    return parsed.astimezone().strftime("%H:%M:%S")


def _full_time(value: str) -> str:
    if not value:
        return "-"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return "-"
    return parsed.astimezone().strftime("%d.%m.%Y %H:%M:%S")


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
    plan_end = _parse_iso(str(shift.get("planEnd") or ""))
    elapsed_ms = int((stamp - started_at).total_seconds() * 1000) if shift_active and started_at is not None else 0

    active_fault = state.get("activeFault") if isinstance(state.get("activeFault"), dict) else None
    active_fault_started = _parse_iso(str(active_fault.get("startedAt") or "")) if active_fault else None
    active_fault_ms = 0
    if shift_active and active_fault_started is not None:
        active_fault_ms = max(0, int((stamp - active_fault_started).total_seconds() * 1000))

    unplanned_ms = max(0, round(_numeric(state.get("unplannedDowntimeMs")))) + active_fault_ms
    runtime_ms = max(0, elapsed_ms - unplanned_ms)
    availability = (runtime_ms / elapsed_ms) if elapsed_ms > 0 else 0.0
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
    elif target_qty > 0:
        expected = float(target_qty)
        performance = (total / expected) if expected > 0 else 0.0
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
        "runtimeMs": runtime_ms,
        "unplannedMs": unplanned_ms,
        "activeFaultMs": active_fault_ms,
        "remainingMs": remaining_ms,
        "targetText": target_text,
        "perfMode": performance_mode,
        "lossPct": loss,
        "colorSummary": color_summary,
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

        if parsed["event_type"] == "queue_enq" and item_key:
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
                    "detected_at": received_at,
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
            items[resolved_key]["released_at"] = received_at
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
            changed = True

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

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .parsers import parse_mega_event_from_log, parse_tablet_fault_line


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
        "version": 2,
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
        "recentItemIds": [],
        "activeFault": None,
        "faultHistory": [],
        "unplannedDowntimeMs": 0,
        "trend": [],
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
    base = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return base.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


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
    return parsed.strftime("%H:%M:%S")


def _full_time(value: str) -> str:
    if not value:
        return "-"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return "-"
    return parsed.strftime("%d.%m.%Y %H:%M:%S")


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
    base["recentItemIds"] = candidate.get("recentItemIds") if isinstance(candidate.get("recentItemIds"), list) else []
    base["activeFault"] = candidate.get("activeFault") if isinstance(candidate.get("activeFault"), dict) else None
    base["faultHistory"] = candidate.get("faultHistory") if isinstance(candidate.get("faultHistory"), list) else []
    base["unplannedDowntimeMs"] = max(0, round(_numeric(candidate.get("unplannedDowntimeMs"))))
    base["trend"] = candidate.get("trend") if isinstance(candidate.get("trend"), list) else []
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


class OeeRuntimeStateManager:
    def __init__(self, path: Path) -> None:
        self.path = path

    def read_state(self) -> dict[str, Any]:
        if not self.path.exists():
            return default_runtime_state()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return default_runtime_state()
        return ensure_runtime_state_shape(payload)

    def write_state(self, state: dict[str, Any]) -> None:
        normalized = ensure_runtime_state_shape(state)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        temp_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(self.path)

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
                state["itemsById"] = {}
                state["recentItemIds"] = []
                state["activeFault"] = None
                state["faultHistory"] = []
                state["unplannedDowntimeMs"] = 0
                state["trend"] = []
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

    def apply_mega_log(self, line: str, received_at: str) -> bool:
        parsed = parse_mega_event_from_log(line)
        if parsed is None:
            return False
        state = self.read_state()
        if not state["shift"]["active"]:
            return False

        changed = False
        now = _parse_iso(received_at) or datetime.now().astimezone()
        item_id = str(parsed.get("item_id") or "").strip()
        measure_id = str(parsed.get("measure_id") or "").strip()
        item_key = item_id or (f"measure:{measure_id}" if measure_id else "")
        items = state["itemsById"] if isinstance(state.get("itemsById"), dict) else {}
        recent_ids = state["recentItemIds"] if isinstance(state.get("recentItemIds"), list) else []
        color = str(parsed.get("color") or "unknown")
        by_color = state["counts"]["byColor"]

        if parsed["event_type"] == "queue_enq" and item_key:
            item = items.get(item_key, {})
            item.update(
                {
                    "item_id": item_id or item.get("item_id") or item_key,
                    "measure_id": measure_id or item.get("measure_id") or "",
                    "color": color,
                    "decision_source": str(parsed.get("decision_source") or item.get("decision_source") or ""),
                    "review_required": bool(parsed.get("review_required")),
                    "detected_at": received_at,
                    "queued_at": received_at,
                    "travel_ms": parsed.get("travel_ms"),
                }
            )
            items[item_key] = item
            recent_ids = [item_key] + [value for value in recent_ids if value != item_key]
            state["recentItemIds"] = recent_ids[:5]
            changed = True

        elif parsed["event_type"] == "pickplace_done":
            if not item_key:
                return False
            item = items.get(item_key, {})
            if item.get("completed_at"):
                return False
            normalized_color = color if color in {"red", "yellow", "blue"} else str(item.get("color") or "blue")
            item.update(
                {
                    "item_id": item_id or item.get("item_id") or item_key,
                    "measure_id": measure_id or item.get("measure_id") or "",
                    "color": normalized_color,
                    "decision_source": str(parsed.get("decision_source") or item.get("decision_source") or ""),
                    "review_required": bool(parsed.get("review_required")),
                    "completed_at": received_at,
                    "classification": "GOOD",
                    "updated_at": received_at,
                }
            )
            items[item_key] = item
            counts = state["counts"]
            counts["total"] = max(0, round(_numeric(counts.get("total")))) + 1
            counts["good"] = max(0, round(_numeric(counts.get("good")))) + 1
            bucket = by_color.get(normalized_color) if isinstance(by_color.get(normalized_color), dict) else None
            if bucket is None:
                by_color[normalized_color] = empty_color_counts()
                bucket = by_color[normalized_color]
            bucket["total"] = max(0, round(_numeric(bucket.get("total")))) + 1
            bucket["good"] = max(0, round(_numeric(bucket.get("good")))) + 1
            recent_ids = [item_key] + [value for value in recent_ids if value != item_key]
            state["recentItemIds"] = recent_ids[:5]
            _set_summary(state, f"#{item.get('item_id') or item_key} tamamlandi ve varsayilan olarak saglam sayildi.", now=now)
            changed = True

        if changed:
            state["itemsById"] = items
            self.write_state(state)
        return changed

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

    def tick(self, *, now: datetime | None = None) -> bool:
        state = self.read_state()
        if not state["shift"]["active"]:
            return False

        stamp = now or datetime.now().astimezone()
        last_logged = _parse_iso(str(state.get("lastSnapshotLoggedAt") or ""))
        if last_logged is not None and (stamp - last_logged).total_seconds() < 5:
            return False

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

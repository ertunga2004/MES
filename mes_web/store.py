from __future__ import annotations

import copy
import threading
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from .config import AppConfig
from .oee_state import build_live_snapshot, build_work_order_snapshot, read_runtime_state_file, shift_options
from .parsers import (
    parse_bridge_status_line,
    parse_mega_event_from_log,
    parse_status_line,
    parse_tablet_fault_line,
    parse_tablet_oee_line,
    parse_vision_event,
    parse_vision_heartbeat,
    parse_vision_status,
    parse_vision_tracks,
)


def utc_now_text(now: datetime | None = None) -> str:
    current = now or datetime.now().astimezone()
    if current.tzinfo is None:
        current = current.astimezone()
    return current.astimezone().isoformat(timespec="milliseconds")


def parse_iso_text(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _clamp_pct(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return round(max(0.0, min(100.0, numeric)), 1)


def _ratio_to_pct(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return round(max(0.0, min(1.0, numeric)) * 100.0, 1)


WORK_ORDER_ACTIVE_STATUSES = {"active", "pending_approval"}


class DashboardStore:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._lock = threading.RLock()
        self._listeners: list[Callable[[str], None]] = []
        self._oee_state_mtime: float | None = None
        self._modules = {
            config.module_id: self._build_module_state(),
        }
        self.refresh_oee_runtime_state(config.module_id, notify=False)

    def _empty_color_totals(self) -> dict[str, dict[str, int]]:
        return {
            color: {"total": 0, "good": 0, "rework": 0, "scrap": 0}
            for color in ("red", "yellow", "blue")
        }

    def _default_vision_status(self) -> dict[str, Any]:
        return {
            "state": "unknown",
            "fps": None,
            "last_seen_at": None,
        }

    def _default_vision_tracks(self) -> dict[str, Any]:
        return {
            "active_tracks": 0,
            "pending_tracks": 0,
            "total_crossings": 0,
            "last_seen_at": None,
        }

    def _default_vision_heartbeat(self) -> dict[str, Any]:
        return {
            "timestamp": None,
            "last_seen_at": None,
        }

    def _default_vision_compare(self) -> dict[str, Any]:
        return {
            "mega": {"red": 0, "yellow": 0, "blue": 0},
            "vision": {"red": 0, "yellow": 0, "blue": 0},
            "diff": {"red": 0, "yellow": 0, "blue": 0},
            "yellow_alarm": "normal",
            "last_updated_at": None,
        }

    def _default_vision_runtime(self) -> dict[str, Any]:
        return {
            "health_state": "offline",
            "mismatch_count": 0,
            "early_accepted_count": 0,
            "early_rejected_count": 0,
            "late_audit_count": 0,
            "last_reject_reason": "",
            "last_item": None,
        }

    def _default_vision_reset(self) -> dict[str, Any]:
        return {
            "at": None,
            "track_crossings_baseline": 0,
            "runtime_metrics_baseline": {
                "mismatch_count": 0,
                "early_accepted_count": 0,
                "early_rejected_count": 0,
                "late_audit_count": 0,
            },
        }

    def _default_vision_state(self) -> dict[str, Any]:
        return {
            "status": self._default_vision_status(),
            "tracks": self._default_vision_tracks(),
            "heartbeat": self._default_vision_heartbeat(),
            "events": deque(maxlen=self.config.vision_event_store_size),
            "compare": self._default_vision_compare(),
            "runtime": self._default_vision_runtime(),
            "reset": self._default_vision_reset(),
        }

    def _default_oee_state(self) -> dict[str, Any]:
        return {
            "enabled": self.config.oee_ui_visible,
            "state_source": "none",
            "updated_at": None,
            "last_tablet_line": "",
            "last_event_summary": "OEE verisi bekleniyor.",
            "header": {
                "line_state": "unknown",
                "state_summary": "Tablet OEE verisi bekleniyor.",
                "tone": "neutral",
            },
            "shift": {
                "active": False,
                "code": "",
                "name": "",
                "started_at": None,
                "ended_at": None,
                "plan_start": None,
                "plan_end": None,
            },
            "targets": {
                "performance_mode": "",
                "target_qty": 0,
                "ideal_cycle_sec": 0.0,
                "planned_stop_min": 0.0,
            },
            "controls": {
                "selected_shift": "SHIFT-A",
                "active_shift_code": "",
                "performance_mode": "TARGET",
                "target_qty": 0,
                "ideal_cycle_sec": 0.0,
                "planned_stop_min": 0.0,
                "quality_override_options": ["GOOD", "REWORK", "SCRAP"],
                "shift_options": shift_options(),
                "can_start": True,
                "can_stop": False,
            },
            "kpis": {
                "oee": None,
                "availability": None,
                "performance": None,
                "quality": None,
            },
            "production": {
                "total": 0,
                "good": 0,
                "rework": 0,
                "scrap": 0,
            },
            "colors": self._empty_color_totals(),
            "trend": [],
            "recent_items": [],
            "quality_override_log": [],
            "fault": {
                "active": False,
                "reason": "Bilinmiyor",
                "status": "Yok",
                "started_at": None,
                "ended_at": None,
                "duration_min": None,
            },
        }

    def _default_work_order_state(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "updated_at": None,
            "controls": {
                "tolerance_minutes": 15.0,
                "can_start": True,
                "can_accept": False,
                "can_rollback": False,
            },
            "summary": {
                "queued_count": 0,
                "active_count": 0,
                "completed_count": 0,
                "inventory_total": 0,
                "last_completed_order_id": "",
                "last_completed_at": None,
            },
            "source": {
                "folder": "",
                "file": "",
                "loaded_at": None,
            },
            "active_order": None,
            "queue": [],
            "completed": [],
            "inventory": [],
            "transition_log": [],
            "completion_log": [],
            "performance_panel": {
                "oee": None,
                "availability": None,
                "performance": None,
                "quality": None,
                "planned_stop_min": 0.0,
                "unplanned_stop_min": 0.0,
                "runtime_min": 0.0,
                "remaining_min": 0.0,
                "active_fault": False,
                "fault_reason": "",
            },
        }

    def _build_module_state(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "mqtt_online": False,
            "last_message_at": None,
            "last_status_at": None,
            "last_log_at": None,
            "last_heartbeat_at": None,
            "last_bridge_status_at": None,
            "last_tablet_log_at": None,
            "last_vision_ingest_at": None,
            "system_status": {
                "mode": "unknown",
                "system_state": "unknown",
                "conveyor_state": "unknown",
                "robot_state": "unknown",
                "last_color": "unknown",
                "step_enabled": None,
                "queue_depth": None,
                "stop_request": None,
            },
            "hardware_status": {
                "direction": "unknown",
                "pwm": None,
                "travel_ms": None,
                "limit_22_pressed": None,
                "limit_23_pressed": None,
                "step_hold": None,
                "step_us": None,
            },
            "bridge": {
                "state": "offline",
                "wifi_connected": None,
                "mqtt_connected": None,
                "queue": None,
                "max_queue": None,
                "drop_uart": None,
                "drop_pub": None,
                "last_rx_ms": None,
                "last_pub_ms": None,
                "uptime_ms": None,
                "rssi": None,
                "last_seen_at": None,
            },
            "counts": {
                "basis": "queue_enq",
                "red": 0,
                "yellow": 0,
                "blue": 0,
                "last_reset_at": None,
            },
            "recent_logs": deque(maxlen=self.config.log_store_size),
            "vision": self._default_vision_state(),
            "oee": self._default_oee_state(),
            "work_orders": self._default_work_order_state(),
        }

    def register_listener(self, listener: Callable[[str], None]) -> None:
        self._listeners.append(listener)

    def _notify(self, module_id: str) -> None:
        for listener in self._listeners:
            listener(module_id)

    def _module(self, module_id: str) -> dict[str, Any]:
        try:
            return self._modules[module_id]
        except KeyError as exc:
            raise KeyError(f"Unknown module: {module_id}") from exc

    def _vision_reset_state(self, module: dict[str, Any]) -> dict[str, Any]:
        vision = module.get("vision")
        if not isinstance(vision, dict):
            vision = self._default_vision_state()
            module["vision"] = vision
        reset = vision.get("reset")
        if not isinstance(reset, dict):
            reset = self._default_vision_reset()
            vision["reset"] = reset
        baseline = reset.get("runtime_metrics_baseline")
        if not isinstance(baseline, dict):
            baseline = self._default_vision_reset()["runtime_metrics_baseline"]
            reset["runtime_metrics_baseline"] = baseline
        return reset

    def _reset_vision_state(self, module: dict[str, Any], *, reset_at: str) -> None:
        current_tracks = module["vision"]["tracks"] if isinstance(module.get("vision"), dict) else {}
        current_runtime = module["vision"]["runtime"] if isinstance(module.get("vision"), dict) else {}
        reset = self._default_vision_reset()
        reset["at"] = reset_at
        reset["track_crossings_baseline"] = max(0, _safe_int(current_tracks.get("total_crossings")))
        reset["runtime_metrics_baseline"] = {
            "mismatch_count": max(0, _safe_int(current_runtime.get("mismatch_count"))),
            "early_accepted_count": max(0, _safe_int(current_runtime.get("early_accepted_count"))),
            "early_rejected_count": max(0, _safe_int(current_runtime.get("early_rejected_count"))),
            "late_audit_count": max(0, _safe_int(current_runtime.get("late_audit_count"))),
        }
        module["last_vision_ingest_at"] = None
        module["vision"] = self._default_vision_state()
        module["vision"]["reset"] = reset

    def _capabilities(self) -> dict[str, bool]:
        return {
            "preset_commands": True,
            "manual_command": True,
            "vision_ingest": self.config.vision_ingest_enabled,
            "vision_ui": self.config.vision_ui_visible,
            "analytics_ui": self.config.analytics_ui_visible,
            "oee_ui": self.config.oee_ui_visible,
        }

    def _refresh_oee_header(self, oee: dict[str, Any]) -> None:
        fault = oee["fault"]
        kpis = oee["kpis"]
        if fault["active"]:
            oee["header"] = {
                "line_state": "stopped",
                "state_summary": fault["reason"] or "Plansiz durus aktif",
                "tone": "bad",
            }
            return
        if oee["shift"]["active"]:
            oee["header"] = {
                "line_state": "running",
                "state_summary": oee["last_event_summary"] or "Aktif vardiya calisiyor.",
                "tone": "good",
            }
            return
        oee_value = kpis["oee"]
        tone = "warn"
        if isinstance(oee_value, (int, float)):
            tone = "good" if oee_value >= 75 else ("warn" if oee_value >= 60 else "bad")
        oee["header"] = {
            "line_state": "ready" if oee["controls"]["selected_shift"] else "unknown",
            "state_summary": oee["last_event_summary"] or "Tablet OEE verisi bekleniyor.",
            "tone": tone,
        }

    def _merge_oee_from_tablet(self, oee: dict[str, Any], parsed: dict[str, Any], *, received_at: str) -> None:
        oee["state_source"] = "tablet_log"
        oee["updated_at"] = received_at
        oee["last_tablet_line"] = parsed["raw_line"]
        oee["kpis"].update(
            {
                "oee": parsed["oee"],
                "availability": parsed["availability"],
                "performance": parsed["performance"],
                "quality": parsed["quality"],
            }
        )
        oee["production"] = copy.deepcopy(parsed["production"])
        oee["colors"] = copy.deepcopy(parsed["colors"])
        oee["last_event_summary"] = "Tablet OEE snapshot alindi."
        trend_row = {
            "time": received_at,
            "oee": parsed["oee"],
            "availability": parsed["availability"],
            "performance": parsed["performance"],
            "quality": parsed["quality"],
            "loss": ((parsed["production"]["scrap"] + parsed["production"]["rework"]) / parsed["production"]["total"] * 100) if parsed["production"]["total"] else 0.0,
        }
        trend = [row for row in oee["trend"] if row.get("time") != received_at]
        trend.append(trend_row)
        oee["trend"] = trend[-10:]
        self._refresh_oee_header(oee)

    def _merge_fault_from_tablet(self, oee: dict[str, Any], parsed: dict[str, Any], *, received_at: str) -> None:
        active = str(parsed["status"] or "").strip().upper() not in {"BITTI", "YOK", "0", "OK", "NORMAL"}
        oee["fault"].update(
            {
                "active": active,
                "reason": parsed["reason"],
                "status": parsed["status"],
                "started_at": parsed["started_at_text"] or (received_at if active else oee["fault"]["started_at"]),
                "ended_at": None if active else (parsed["ended_at_text"] or received_at),
                "duration_min": parsed["duration_min"],
            }
        )
        oee["updated_at"] = received_at
        oee["last_event_summary"] = f"Tablet fault status: {parsed['status']}"
        self._refresh_oee_header(oee)

    def refresh_oee_runtime_state(self, module_id: str, *, notify: bool = True, force: bool = False) -> bool:
        path = self.config.oee_runtime_state_path
        if not path.exists():
            return False

        try:
            mtime = path.stat().st_mtime
        except OSError:
            return False
        if not force and self._oee_state_mtime == mtime:
            return False

        payload = read_runtime_state_file(Path(path))
        if payload is None:
            return False

        with self._lock:
            module = self._module(module_id)
            oee = module["oee"]
            shift = payload.get("shift") or {}
            summary_text = str(payload.get("lastEventSummary") or oee["last_event_summary"])
            target_qty = _safe_int(payload.get("targetQty") or shift.get("targetQty") or 0)
            ideal_cycle_sec = _safe_float(payload.get("idealCycleSec") or shift.get("idealCycleSec") or 0.0)
            planned_stop_min = _safe_float(payload.get("plannedStopMin") or shift.get("plannedStopMin") or 0.0)
            oee["enabled"] = self.config.oee_ui_visible
            oee["state_source"] = "runtime_state"
            oee["updated_at"] = payload.get("lastUpdatedAt") or payload.get("lastSnapshotLoggedAt") or oee["updated_at"]
            oee["last_event_summary"] = summary_text
            oee["last_tablet_line"] = payload.get("lastTabletLine") or oee["last_tablet_line"]
            oee["shift"] = {
                "active": bool(shift.get("active")),
                "code": str(shift.get("code") or ""),
                "name": str(shift.get("name") or ""),
                "started_at": shift.get("startedAt"),
                "ended_at": shift.get("endedAt"),
                "plan_start": shift.get("planStart"),
                "plan_end": shift.get("planEnd"),
            }
            oee["targets"] = {
                "performance_mode": str(payload.get("performanceMode") or shift.get("performanceMode") or ""),
                "target_qty": target_qty,
                "ideal_cycle_sec": ideal_cycle_sec,
                "planned_stop_min": planned_stop_min,
            }
            oee["controls"] = {
                "selected_shift": str(payload.get("shiftSelected") or oee["shift"]["code"] or "SHIFT-A"),
                "active_shift_code": oee["shift"]["code"],
                "performance_mode": oee["targets"]["performance_mode"] or "TARGET",
                "target_qty": target_qty,
                "ideal_cycle_sec": ideal_cycle_sec,
                "planned_stop_min": planned_stop_min,
                "quality_override_options": ["GOOD", "REWORK", "SCRAP"],
                "shift_options": shift_options(),
                "can_start": not bool(oee["shift"]["active"]),
                "can_stop": bool(oee["shift"]["active"]),
            }

            live = build_live_snapshot(payload, now=datetime.now().astimezone())
            oee["production"] = {
                "total": int(live["total"]),
                "good": int(live["good"]),
                "rework": int(live["rework"]),
                "scrap": int(live["scrap"]),
            }
            oee["colors"] = {
                color: {
                    "total": int(live["colorSummary"][color]["total"]),
                    "good": int(live["colorSummary"][color]["good"]),
                    "rework": int(live["colorSummary"][color]["rework"]),
                    "scrap": int(live["colorSummary"][color]["scrap"]),
                }
                for color in ("red", "yellow", "blue")
            }
            oee["kpis"] = {
                "oee": _ratio_to_pct(live["oee"]),
                "availability": _ratio_to_pct(live["availability"]),
                "performance": _ratio_to_pct(live["performance"]),
                "quality": _ratio_to_pct(live["quality"]),
            }

            trend = []
            for row in (payload.get("trend") or [])[-10:]:
                trend.append(
                    {
                        "time": row.get("time"),
                        "oee": _clamp_pct(row.get("oee")),
                        "availability": _clamp_pct(row.get("availability")),
                        "performance": _clamp_pct(row.get("performance")),
                        "quality": _clamp_pct(row.get("quality")),
                        "loss": _clamp_pct(row.get("loss")),
                    }
                )
            oee["trend"] = trend
            items = payload.get("itemsById") if isinstance(payload.get("itemsById"), dict) else {}
            recent_item_ids = payload.get("recentItemIds") if isinstance(payload.get("recentItemIds"), list) else []
            recent_items: list[dict[str, Any]] = []
            for item_key in recent_item_ids:
                item = items.get(item_key)
                if not isinstance(item, dict) or not item.get("completed_at"):
                    continue
                recent_items.append(
                    {
                        "item_id": str(item.get("item_id") or item_key),
                        "measure_id": str(item.get("measure_id") or ""),
                        "color": str(item.get("color") or ""),
                        "sensor_color": str(item.get("sensor_color") or ""),
                        "vision_color": str(item.get("vision_color") or ""),
                        "final_color": str(item.get("final_color") or item.get("color") or ""),
                        "classification": str(item.get("classification") or "GOOD"),
                        "completed_at": item.get("completed_at"),
                        "updated_at": item.get("updated_at"),
                        "decision_source": str(item.get("decision_source") or ""),
                        "finalization_reason": str(item.get("finalization_reason") or ""),
                        "correlation_status": str(item.get("correlation_status") or ""),
                        "pick_trigger_source": str(item.get("pick_trigger_source") or ""),
                        "review_required": bool(item.get("review_required")),
                    }
                )
            oee["recent_items"] = recent_items
            oee["quality_override_log"] = copy.deepcopy((payload.get("qualityOverrideLog") or [])[:10])
            work_orders_payload = payload.get("workOrders") if isinstance(payload.get("workOrders"), dict) else {}
            raw_work_orders = work_orders_payload.get("ordersById") if isinstance(work_orders_payload.get("ordersById"), dict) else {}
            raw_sequence = work_orders_payload.get("orderSequence") if isinstance(work_orders_payload.get("orderSequence"), list) else []

            def project_work_order(order_id: str, order: dict[str, Any]) -> dict[str, Any]:
                metrics = build_work_order_snapshot(payload, order, now=datetime.now().astimezone())
                status = str(order.get("status") or "queued")
                quantity = max(0, _safe_int(order.get("quantity")))
                completed_qty = max(0, _safe_int(order.get("completedQty")))
                inventory_qty = max(0, _safe_int(order.get("inventoryConsumedQty")))
                production_qty = max(0, _safe_int(order.get("productionQty")))
                remaining_qty = max(0, quantity - completed_qty)
                requirements_payload = order.get("requirements") if isinstance(order.get("requirements"), list) else []
                requirements: list[dict[str, Any]] = []
                for requirement in requirements_payload:
                    if not isinstance(requirement, dict):
                        continue
                    requirement_qty = max(0, _safe_int(requirement.get("quantity")))
                    requirement_completed = max(0, _safe_int(requirement.get("completedQty")))
                    requirement_inventory = max(0, _safe_int(requirement.get("inventoryConsumedQty")))
                    requirement_production = max(0, _safe_int(requirement.get("productionQty")))
                    requirement_remaining = max(0, requirement_qty - requirement_completed)
                    requirements.append(
                        {
                            "line_id": str(requirement.get("lineId") or ""),
                            "product_code": str(requirement.get("productCode") or ""),
                            "stock_code": str(requirement.get("stockCode") or ""),
                            "stock_name": str(requirement.get("stockName") or ""),
                            "color": str(requirement.get("color") or ""),
                            "match_key": str(requirement.get("matchKey") or ""),
                            "qty": requirement_qty,
                            "completed_qty": requirement_completed,
                            "inventory_consumed_qty": requirement_inventory,
                            "production_qty": requirement_production,
                            "remaining_qty": requirement_remaining,
                            "progress_pct": round((requirement_completed / requirement_qty) * 100.0, 1) if requirement_qty > 0 else 0.0,
                        }
                    )
                return {
                    "order_id": order_id,
                    "erp_type": str(order.get("erpType") or "İş Emirleri"),
                    "date": order.get("date"),
                    "system_no": str(order.get("systemNo") or ""),
                    "sequence_no": max(0, _safe_int(order.get("sequenceNo"))),
                    "locked": bool(order.get("locked")),
                    "stock_type": str(order.get("stockType") or ""),
                    "stock_code": str(order.get("stockCode") or ""),
                    "stock_name": str(order.get("stockName") or ""),
                    "unit": str(order.get("unit") or ""),
                    "method_code": str(order.get("methodCode") or ""),
                    "qty": quantity,
                    "project_code": str(order.get("projectCode") or ""),
                    "description": str(order.get("description") or ""),
                    "work_center_code": str(order.get("workCenterCode") or ""),
                    "operation_code": str(order.get("operationCode") or ""),
                    "setup_time_sec": _safe_float(order.get("setupTimeSec")),
                    "worker_count": max(0, _safe_int(order.get("workerCount"))),
                    "cycle_time_sec": _safe_float(order.get("cycleTimeSec")),
                    "shift_code": str(order.get("shiftCode") or ""),
                    "product_code": str(order.get("productCode") or ""),
                    "product_color": str(order.get("productColor") or ""),
                    "requirements": requirements,
                    "status": status,
                    "queued_at": order.get("queuedAt"),
                    "started_at": order.get("startedAt"),
                    "auto_completed_at": order.get("autoCompletedAt"),
                    "completed_at": order.get("completedAt"),
                    "started_by": str(order.get("startedBy") or ""),
                    "started_by_name": str(order.get("startedByName") or ""),
                    "transition_reason": str(order.get("transitionReason") or ""),
                    "acceptance_pending": status == "pending_approval",
                    "inventory_consumed_qty": inventory_qty,
                    "production_qty": production_qty,
                    "completed_qty": completed_qty,
                    "remaining_qty": remaining_qty,
                    "progress_pct": round((completed_qty / quantity) * 100.0, 1) if quantity > 0 else 0.0,
                    "last_allocation_at": order.get("lastAllocationAt"),
                    "good_qty": int(metrics["goodQty"]),
                    "rework_qty": int(metrics["reworkQty"]),
                    "scrap_qty": int(metrics["scrapQty"]),
                    "ideal_cycle_sec": round(float(metrics["idealCycleSec"]), 1),
                    "planned_duration_min": round(float(metrics["plannedDurationMs"]) / 60000.0, 1),
                    "runtime_min": round(float(metrics["runtimeMs"]) / 60000.0, 1),
                    "unplanned_stop_min": round(float(metrics["unplannedMs"]) / 60000.0, 1),
                    "availability": None,
                    "performance": _ratio_to_pct(metrics["performance"]),
                    "quality": _ratio_to_pct(metrics["quality"]),
                    "oee": None,
                }

            projected_by_id: dict[str, dict[str, Any]] = {}
            projected_sequence: list[str] = []
            for order_id in raw_sequence:
                normalized_id = str(order_id or "").strip()
                order = raw_work_orders.get(normalized_id)
                if not normalized_id or not isinstance(order, dict):
                    continue
                projected_by_id[normalized_id] = project_work_order(normalized_id, order)
                projected_sequence.append(normalized_id)
            for order_id, order in raw_work_orders.items():
                normalized_id = str(order_id or "").strip()
                if not normalized_id or normalized_id in projected_by_id or not isinstance(order, dict):
                    continue
                projected_by_id[normalized_id] = project_work_order(normalized_id, order)
                projected_sequence.append(normalized_id)

            active_order_id = str(work_orders_payload.get("activeOrderId") or "").strip()
            active_order = projected_by_id.get(active_order_id)
            if active_order is None:
                active_order = next((row for row in projected_by_id.values() if row["status"] in WORK_ORDER_ACTIVE_STATUSES), None)

            queue_orders = [projected_by_id[order_id] for order_id in projected_sequence if projected_by_id.get(order_id, {}).get("status") == "queued"]
            completed_orders = [projected_by_id[order_id] for order_id in projected_sequence if projected_by_id.get(order_id, {}).get("status") == "completed"]
            inventory_payload = work_orders_payload.get("inventoryByProduct") if isinstance(work_orders_payload.get("inventoryByProduct"), dict) else {}
            inventory_rows: list[dict[str, Any]] = []
            for match_key, row in inventory_payload.items():
                if not isinstance(row, dict):
                    continue
                quantity = max(0, _safe_int(row.get("quantity")))
                if quantity <= 0:
                    continue
                inventory_rows.append(
                    {
                        "match_key": str(match_key or ""),
                        "product_code": str(row.get("productCode") or ""),
                        "stock_code": str(row.get("stockCode") or ""),
                        "stock_name": str(row.get("stockName") or ""),
                        "color": str(row.get("color") or ""),
                        "quantity": quantity,
                        "last_updated_at": row.get("lastUpdatedAt"),
                        "last_source": str(row.get("lastSource") or ""),
                    }
                )
            inventory_rows.sort(key=lambda row: (-row["quantity"], row["stock_code"], row["match_key"]))

            module["work_orders"] = {
                "enabled": True,
                "updated_at": payload.get("lastUpdatedAt") or payload.get("lastSnapshotLoggedAt") or module["work_orders"].get("updated_at"),
                "controls": {
                    "tolerance_minutes": _safe_float(work_orders_payload.get("toleranceMinutes") or 0.0),
                    "can_start": active_order is None,
                    "can_accept": bool(active_order and active_order.get("status") == "pending_approval"),
                    "can_rollback": active_order is not None,
                },
                "summary": {
                    "queued_count": len(queue_orders),
                    "active_count": 1 if active_order is not None else 0,
                    "completed_count": len(completed_orders),
                    "inventory_total": sum(row["quantity"] for row in inventory_rows),
                    "last_completed_order_id": str(work_orders_payload.get("lastCompletedOrderId") or ""),
                    "last_completed_at": work_orders_payload.get("lastCompletedAt"),
                },
                "source": {
                    "folder": str(((work_orders_payload.get("source") or {}) if isinstance(work_orders_payload.get("source"), dict) else {}).get("folder") or self.config.work_orders_dir),
                    "file": str(((work_orders_payload.get("source") or {}) if isinstance(work_orders_payload.get("source"), dict) else {}).get("file") or ""),
                    "loaded_at": (((work_orders_payload.get("source") or {}) if isinstance(work_orders_payload.get("source"), dict) else {}).get("loadedAt")),
                },
                "active_order": copy.deepcopy(active_order) if isinstance(active_order, dict) else None,
                "queue": copy.deepcopy(queue_orders),
                "completed": copy.deepcopy(completed_orders[:10]),
                "inventory": copy.deepcopy(inventory_rows[:12]),
                "transition_log": copy.deepcopy((work_orders_payload.get("transitionLog") or [])[:10]),
                "completion_log": copy.deepcopy((work_orders_payload.get("completionLog") or [])[:10]),
                "performance_panel": {
                    "oee": _ratio_to_pct(live["oee"]),
                    "availability": _ratio_to_pct(live["availability"]),
                    "performance": _ratio_to_pct(live["performance"]),
                    "quality": _ratio_to_pct(live["quality"]),
                    "planned_stop_min": round(float(live["plannedStopMs"]) / 60000.0, 1),
                    "unplanned_stop_min": round(float(live["unplannedMs"]) / 60000.0, 1),
                    "runtime_min": round(float(live["runtimeMs"]) / 60000.0, 1),
                    "remaining_min": round(float(live["remainingMs"]) / 60000.0, 1),
                    "active_fault": bool(oee["fault"]["active"]),
                    "fault_reason": str(oee["fault"]["reason"] or ""),
                },
            }
            vision_state = payload.get("vision") if isinstance(payload.get("vision"), dict) else {}
            vision_metrics = vision_state.get("metrics") if isinstance(vision_state.get("metrics"), dict) else {}
            vision_reset = self._vision_reset_state(module)
            metrics_baseline = vision_reset.get("runtime_metrics_baseline")
            if not isinstance(metrics_baseline, dict):
                metrics_baseline = self._default_vision_reset()["runtime_metrics_baseline"]
                vision_reset["runtime_metrics_baseline"] = metrics_baseline
            reset_at = parse_iso_text(str(vision_reset.get("at") or ""))
            raw_mismatch_count = max(0, _safe_int(vision_metrics.get("mismatchCount")))
            raw_early_accepted_count = max(0, _safe_int(vision_metrics.get("earlyAcceptedCount")))
            raw_early_rejected_count = max(0, _safe_int(vision_metrics.get("earlyRejectedCount")))
            raw_late_audit_count = max(0, _safe_int(vision_metrics.get("lateAuditCount")))
            baseline_mismatch_count = max(0, _safe_int(metrics_baseline.get("mismatch_count")))
            baseline_early_accepted_count = max(0, _safe_int(metrics_baseline.get("early_accepted_count")))
            baseline_early_rejected_count = max(0, _safe_int(metrics_baseline.get("early_rejected_count")))
            baseline_late_audit_count = max(0, _safe_int(metrics_baseline.get("late_audit_count")))
            if raw_mismatch_count < baseline_mismatch_count:
                baseline_mismatch_count = 0
                metrics_baseline["mismatch_count"] = 0
            if raw_early_accepted_count < baseline_early_accepted_count:
                baseline_early_accepted_count = 0
                metrics_baseline["early_accepted_count"] = 0
            if raw_early_rejected_count < baseline_early_rejected_count:
                baseline_early_rejected_count = 0
                metrics_baseline["early_rejected_count"] = 0
            if raw_late_audit_count < baseline_late_audit_count:
                baseline_late_audit_count = 0
                metrics_baseline["late_audit_count"] = 0
            last_item = recent_items[0] if recent_items else None
            if isinstance(last_item, dict) and reset_at is not None:
                item_time = parse_iso_text(str(last_item.get("updated_at") or last_item.get("completed_at") or ""))
                if item_time is not None and item_time <= reset_at:
                    last_item = None
            mismatch_count = max(0, raw_mismatch_count - baseline_mismatch_count)
            early_accepted_count = max(0, raw_early_accepted_count - baseline_early_accepted_count)
            early_rejected_count = max(0, raw_early_rejected_count - baseline_early_rejected_count)
            late_audit_count = max(0, raw_late_audit_count - baseline_late_audit_count)
            module["vision"]["runtime"] = {
                "health_state": str(vision_state.get("healthState") or "offline"),
                "mismatch_count": mismatch_count,
                "early_accepted_count": early_accepted_count,
                "early_rejected_count": early_rejected_count,
                "late_audit_count": late_audit_count,
                "last_reject_reason": str(vision_state.get("lastRejectReason") or "") if early_rejected_count > 0 else "",
                "last_item": copy.deepcopy(last_item) if isinstance(last_item, dict) else None,
            }
            active_fault = payload.get("activeFault")
            if isinstance(active_fault, dict):
                oee["fault"].update(
                    {
                        "active": True,
                        "reason": str(active_fault.get("reason") or "Bilinmiyor"),
                        "status": str(active_fault.get("status") or "BASLADI"),
                        "started_at": active_fault.get("startedAt"),
                        "ended_at": active_fault.get("endedAt"),
                        "duration_min": active_fault.get("durationMin"),
                    }
                )
            elif active_fault is None:
                oee["fault"].update({"active": False, "status": "BITTI"})

            last_tablet_line = oee["last_tablet_line"]
            parsed_oee = parse_tablet_oee_line(last_tablet_line) if last_tablet_line else None
            if parsed_oee is not None and not oee["shift"]["active"] and oee["production"]["total"] == 0:
                self._merge_oee_from_tablet(oee, parsed_oee, received_at=oee["updated_at"] or utc_now_text())
                oee["state_source"] = "runtime_state"
            oee["last_event_summary"] = summary_text
            self._refresh_oee_header(oee)

        self._oee_state_mtime = mtime
        if notify:
            self._notify(module_id)
        return True

    def modules_summary(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    "module_id": self.config.module_id,
                    "module_type": self.config.module_type,
                    "title": self.config.module_title,
                    "enabled": self._modules[self.config.module_id]["enabled"],
                    "ui_phase": self.config.ui_phase,
                    "capabilities": self._capabilities(),
                }
            ]

    def set_mqtt_connection(self, online: bool) -> None:
        with self._lock:
            module = self._module(self.config.module_id)
            if module["mqtt_online"] == online:
                return
            module["mqtt_online"] = online
        self._notify(self.config.module_id)

    def _touch_message(self, module_id: str, received_at: str) -> dict[str, Any]:
        module = self._module(module_id)
        module["last_message_at"] = received_at
        return module

    def apply_status_line(self, module_id: str, line: str, *, received_at: str | None = None) -> None:
        parsed = parse_status_line(line)
        if parsed is None:
            return
        stamp = received_at or utc_now_text()
        normalized = str(line or "").strip()
        with self._lock:
            module = self._touch_message(module_id, stamp)
            module["last_status_at"] = stamp
            module["system_status"].update(
                {
                    "mode": parsed["mode"],
                    "system_state": parsed["system_state"],
                    "conveyor_state": parsed["conveyor_state"],
                    "robot_state": parsed["robot_state"],
                    "last_color": parsed["last_color"],
                    "step_enabled": parsed["step_enabled"],
                    "queue_depth": parsed["queue_depth"],
                    "stop_request": parsed["stop_request"],
                }
            )
            module["hardware_status"].update(
                {
                    "direction": parsed["direction"],
                    "pwm": parsed["pwm"],
                    "travel_ms": parsed["travel_ms"],
                    "limit_22_pressed": parsed["limit_22_pressed"],
                    "limit_23_pressed": parsed["limit_23_pressed"],
                    "step_hold": parsed["step_hold"],
                    "step_us": parsed["step_us"],
                }
            )
            self._append_recent_log(module, self.config.topics["status"], normalized, stamp)
        self._notify(module_id)

    def _append_recent_log(self, module: dict[str, Any], topic: str, line: str, received_at: str) -> None:
        if topic in {self.config.topics["logs"], self.config.topics["status"]}:
            source = "mega"
        elif topic == self.config.topics["tablet_log"]:
            source = "tablet"
        elif topic == self.config.topics["bridge_status"]:
            source = "bridge"
        else:
            source = "system"
        module["recent_logs"].append(
            {
                "id": uuid.uuid4().hex[:12],
                "source": source,
                "topic": topic,
                "message": line,
                "received_at": received_at,
            }
        )

    def append_system_log(
        self,
        module_id: str,
        message: str,
        *,
        topic: str = "local/system",
        received_at: str | None = None,
    ) -> None:
        stamp = received_at or utc_now_text()
        with self._lock:
            module = self._touch_message(module_id, stamp)
            module["last_log_at"] = stamp
            self._append_recent_log(module, topic, str(message).strip(), stamp)
        self._notify(module_id)

    def _recompute_compare(self, module: dict[str, Any], received_at: str) -> None:
        compare = module["vision"]["compare"]
        compare["diff"] = {
            color: compare["mega"][color] - compare["vision"][color]
            for color in ("red", "yellow", "blue")
        }
        compare["yellow_alarm"] = "alarm" if abs(compare["diff"]["yellow"]) > 1 else "normal"
        compare["last_updated_at"] = received_at

    def _increment_compare(self, module: dict[str, Any], source: str, color: str, received_at: str) -> None:
        if color not in {"red", "yellow", "blue"}:
            return
        compare = module["vision"]["compare"]
        compare[source][color] += 1
        self._recompute_compare(module, received_at)

    def apply_log_line(
        self,
        module_id: str,
        line: str,
        *,
        topic: str | None = None,
        received_at: str | None = None,
    ) -> None:
        stamp = received_at or utc_now_text()
        topic_name = topic or self.config.topics["logs"]
        with self._lock:
            module = self._touch_message(module_id, stamp)
            module["last_log_at"] = stamp
            normalized = str(line or "").strip()
            self._append_recent_log(module, topic_name, normalized, stamp)

            if normalized == "__reset_counts__":
                module["counts"]["red"] = 0
                module["counts"]["yellow"] = 0
                module["counts"]["blue"] = 0
                module["counts"]["last_reset_at"] = stamp
                self._reset_vision_state(module, reset_at=stamp)
            else:
                event = parse_mega_event_from_log(normalized)
                if event and event["event_type"] == "queue_enq":
                    color = event["color"]
                    if color in {"red", "yellow", "blue"}:
                        module["counts"][color] += 1
                        self._increment_compare(module, "mega", color, stamp)
        self._notify(module_id)

    def apply_heartbeat(self, module_id: str, *, received_at: str | None = None) -> None:
        stamp = received_at or utc_now_text()
        with self._lock:
            module = self._touch_message(module_id, stamp)
            module["last_heartbeat_at"] = stamp
        self._notify(module_id)

    def apply_bridge_status(self, module_id: str, line: str, *, received_at: str | None = None) -> None:
        parsed = parse_bridge_status_line(line)
        if parsed is None:
            return
        stamp = received_at or utc_now_text()
        with self._lock:
            module = self._touch_message(module_id, stamp)
            module["last_bridge_status_at"] = stamp
            module["bridge"].update(parsed)
            module["bridge"]["last_seen_at"] = stamp
        self._notify(module_id)

    def apply_tablet_log(self, module_id: str, payload: str, *, received_at: str | None = None) -> None:
        stamp = received_at or utc_now_text()
        parsed_oee = parse_tablet_oee_line(payload)
        parsed_fault = parse_tablet_fault_line(payload)
        with self._lock:
            module = self._touch_message(module_id, stamp)
            module["last_tablet_log_at"] = stamp
            if parsed_oee is not None and not module["oee"]["shift"]["active"] and module["oee"]["production"]["total"] == 0:
                self._merge_oee_from_tablet(module["oee"], parsed_oee, received_at=stamp)
            if parsed_fault is not None:
                self._merge_fault_from_tablet(module["oee"], parsed_fault, received_at=stamp)
        self._notify(module_id)

    def apply_vision_status(self, module_id: str, payload: Any, *, received_at: str | None = None) -> None:
        if not self.config.vision_ingest_enabled:
            return
        parsed = parse_vision_status(payload)
        if parsed is None:
            return
        stamp = received_at or utc_now_text()
        with self._lock:
            module = self._touch_message(module_id, stamp)
            module["last_vision_ingest_at"] = stamp
            module["vision"]["status"].update(parsed)
            module["vision"]["status"]["last_seen_at"] = stamp
        self._notify(module_id)

    def apply_vision_tracks(self, module_id: str, payload: Any, *, received_at: str | None = None) -> None:
        if not self.config.vision_ingest_enabled:
            return
        parsed = parse_vision_tracks(payload)
        if parsed is None:
            return
        stamp = received_at or utc_now_text()
        with self._lock:
            module = self._touch_message(module_id, stamp)
            module["last_vision_ingest_at"] = stamp
            reset = self._vision_reset_state(module)
            baseline = max(0, _safe_int(reset.get("track_crossings_baseline")))
            raw_crossings = max(0, _safe_int(parsed.get("total_crossings")))
            if raw_crossings < baseline:
                baseline = 0
                reset["track_crossings_baseline"] = 0
            next_tracks = dict(parsed)
            next_tracks["total_crossings"] = max(0, raw_crossings - baseline)
            module["vision"]["tracks"].update(next_tracks)
            module["vision"]["tracks"]["last_seen_at"] = stamp
        self._notify(module_id)

    def apply_vision_heartbeat(self, module_id: str, payload: Any, *, received_at: str | None = None) -> None:
        if not self.config.vision_ingest_enabled:
            return
        parsed = parse_vision_heartbeat(payload)
        if parsed is None:
            return
        stamp = received_at or utc_now_text()
        with self._lock:
            module = self._touch_message(module_id, stamp)
            module["last_vision_ingest_at"] = stamp
            module["vision"]["heartbeat"].update(parsed)
            module["vision"]["heartbeat"]["last_seen_at"] = stamp
        self._notify(module_id)

    def apply_vision_event(self, module_id: str, payload: Any, *, received_at: str | None = None) -> None:
        if not self.config.vision_ingest_enabled:
            return
        parsed = parse_vision_event(payload)
        if parsed is None:
            return
        stamp = received_at or utc_now_text()
        with self._lock:
            module = self._touch_message(module_id, stamp)
            module["last_vision_ingest_at"] = stamp
            module["vision"]["events"].append(
                {
                    "id": uuid.uuid4().hex[:12],
                    "source": "vision",
                    "event_type": parsed["event_type"],
                    "color": parsed["color"],
                    "track_id": parsed["track_id"],
                    "item_id": parsed.get("item_id"),
                    "measure_id": parsed.get("measure_id"),
                    "confidence": parsed.get("confidence"),
                    "confidence_tier": parsed.get("confidence_tier"),
                    "correlation_status": parsed.get("correlation_status"),
                    "late_vision_audit_flag": bool(parsed.get("late_vision_audit_flag")),
                    "notes": parsed["notes"],
                    "received_at": stamp,
                }
            )
            compare_color = parsed["compare_color"]
            if compare_color:
                self._increment_compare(module, "vision", compare_color, stamp)
        self._notify(module_id)

    def reset_counts(self, module_id: str, *, received_at: str | None = None) -> None:
        stamp = received_at or utc_now_text()
        with self._lock:
            module = self._module(module_id)
            module["counts"]["red"] = 0
            module["counts"]["yellow"] = 0
            module["counts"]["blue"] = 0
            module["counts"]["last_reset_at"] = stamp
            self._reset_vision_state(module, reset_at=stamp)
            self._append_recent_log(module, "local/system", "SYSTEM|COUNTS|RESET", stamp)
        self._notify(module_id)

    def command_permissions(self) -> dict[str, Any]:
        mode = str(self.config.command_mode or "full_live").strip().lower()
        if mode == "read_only":
            publish_enabled = False
            manual_command_enabled = False
        elif mode == "preset_live":
            publish_enabled = self.config.publish_enabled
            manual_command_enabled = False
        else:
            mode = "full_live" if mode in {"live", "shadow", ""} else mode
            publish_enabled = self.config.publish_enabled
            manual_command_enabled = publish_enabled and self.config.manual_command_enabled

        return {
            "mode": mode,
            "publish_enabled": publish_enabled,
            "manual_command_enabled": manual_command_enabled,
            "allowed_presets": list(self.config.allowed_presets),
            "transport_topic": self.config.topics["command"],
        }

    def connection_fingerprint(self, module_id: str, *, now: datetime | None = None) -> tuple[Any, ...]:
        snapshot = self.get_dashboard_snapshot(module_id, now=now)
        bridge = snapshot["connection"]["bridge"]
        heartbeat = snapshot["connection"]["mega_heartbeat"]
        mqtt = snapshot["connection"]["mqtt"]
        return (
            mqtt["state"],
            heartbeat["state"],
            bridge["state"],
            bridge["queue"],
            bridge["drop_uart"],
            bridge["drop_pub"],
        )

    def get_dashboard_snapshot(self, module_id: str, *, now: datetime | None = None) -> dict[str, Any]:
        current = now or datetime.now(timezone.utc)
        snapshot_at = utc_now_text(current)
        with self._lock:
            module = self._module(module_id)
            heartbeat_last_seen = parse_iso_text(module["last_heartbeat_at"])
            bridge_last_seen = parse_iso_text(module["bridge"]["last_seen_at"])

            heartbeat_online = bool(
                heartbeat_last_seen
                and current - heartbeat_last_seen <= timedelta(seconds=self.config.heartbeat_timeout_sec)
            )
            if bridge_last_seen is None:
                bridge_state = "offline"
            elif current - bridge_last_seen > timedelta(seconds=self.config.bridge_stale_after_sec):
                bridge_state = "offline"
            else:
                bridge_state = module["bridge"]["state"]

            counts = copy.deepcopy(module["counts"])
            counts["total"] = counts["red"] + counts["yellow"] + counts["blue"]

            recent_logs = list(module["recent_logs"])[-self.config.log_response_size :]
            recent_logs.reverse()

            vision_status = copy.deepcopy(module["vision"]["status"])
            vision_tracks = copy.deepcopy(module["vision"]["tracks"])
            vision_compare = copy.deepcopy(module["vision"]["compare"])
            vision_runtime = copy.deepcopy(module["vision"]["runtime"])

            return {
                "module_meta": {
                    "module_id": self.config.module_id,
                    "module_type": self.config.module_type,
                    "title": self.config.module_title,
                    "ui_phase": self.config.ui_phase,
                    "capabilities": self._capabilities(),
                },
                "connection": {
                    "mqtt": {
                        "state": "online" if module["mqtt_online"] else "offline",
                        "last_message_at": module["last_message_at"],
                    },
                    "mega_heartbeat": {
                        "state": "online" if heartbeat_online else "offline",
                        "timeout_sec": self.config.heartbeat_timeout_sec,
                        "last_seen_at": module["last_heartbeat_at"],
                    },
                    "bridge": {
                        "state": bridge_state,
                        "wifi_connected": module["bridge"]["wifi_connected"],
                        "mqtt_connected": module["bridge"]["mqtt_connected"],
                        "queue": module["bridge"]["queue"],
                        "max_queue": module["bridge"]["max_queue"],
                        "drop_uart": module["bridge"]["drop_uart"],
                        "drop_pub": module["bridge"]["drop_pub"],
                        "last_rx_ms": module["bridge"]["last_rx_ms"],
                        "last_pub_ms": module["bridge"]["last_pub_ms"],
                        "uptime_ms": module["bridge"]["uptime_ms"],
                        "rssi": module["bridge"]["rssi"],
                        "last_seen_at": module["bridge"]["last_seen_at"],
                    },
                },
                "system_status": copy.deepcopy(module["system_status"]),
                "hardware_status": {
                    **copy.deepcopy(module["hardware_status"]),
                    "esp32_state": "online" if heartbeat_online else "offline",
                },
                "counts": counts,
                "recent_logs": recent_logs,
                "command_permissions": self.command_permissions(),
                "timestamps": {
                    "snapshot_at": snapshot_at,
                    "last_status_at": module["last_status_at"],
                    "last_log_at": module["last_log_at"],
                    "last_heartbeat_at": module["last_heartbeat_at"],
                    "last_bridge_status_at": module["last_bridge_status_at"],
                    "last_tablet_log_at": module["last_tablet_log_at"],
                    "last_vision_ingest_at": module["last_vision_ingest_at"],
                },
                "vision_ingest": {
                    "enabled": self.config.vision_ingest_enabled,
                    "ui_visible": self.config.vision_ui_visible,
                    "status": vision_status,
                    "tracks": vision_tracks,
                    "compare": vision_compare,
                    "runtime": vision_runtime,
                },
                "oee": copy.deepcopy(module["oee"]),
                "work_orders": copy.deepcopy(module["work_orders"]),
            }

from __future__ import annotations

import copy
import json
import threading
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .config import AppConfig
from .oee_state import build_live_snapshot, shift_options
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
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


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
            "fault": {
                "active": False,
                "reason": "Bilinmiyor",
                "status": "Yok",
                "started_at": None,
                "ended_at": None,
                "duration_min": None,
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
                "drop_uart": None,
                "drop_pub": None,
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
            "vision": {
                "status": {
                    "state": "unknown",
                    "fps": None,
                    "last_seen_at": None,
                },
                "tracks": {
                    "active_tracks": 0,
                    "pending_tracks": 0,
                    "total_crossings": 0,
                    "last_seen_at": None,
                },
                "heartbeat": {
                    "timestamp": None,
                    "last_seen_at": None,
                },
                "events": deque(maxlen=self.config.vision_event_store_size),
                "compare": {
                    "mega": {"red": 0, "yellow": 0, "blue": 0},
                    "vision": {"red": 0, "yellow": 0, "blue": 0},
                    "diff": {"red": 0, "yellow": 0, "blue": 0},
                    "yellow_alarm": "normal",
                    "last_updated_at": None,
                },
            },
            "oee": self._default_oee_state(),
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

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
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
                "oee": round(float(live["oee"]) * 100.0, 1),
                "availability": round(float(live["availability"]) * 100.0, 1),
                "performance": round(float(live["performance"]) * 100.0, 1),
                "quality": round(float(live["quality"]) * 100.0, 1),
            }

            trend = []
            for row in (payload.get("trend") or [])[-10:]:
                trend.append(
                    {
                        "time": row.get("time"),
                        "oee": row.get("oee"),
                        "availability": row.get("availability"),
                        "performance": row.get("performance"),
                        "quality": row.get("quality"),
                        "loss": row.get("loss"),
                    }
                )
            oee["trend"] = trend
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
        self._notify(module_id)

    def _append_recent_log(self, module: dict[str, Any], topic: str, line: str, received_at: str) -> None:
        source = "mega" if topic == self.config.topics["logs"] else "system"
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
            module["vision"]["tracks"].update(parsed)
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
                        "drop_uart": module["bridge"]["drop_uart"],
                        "drop_pub": module["bridge"]["drop_pub"],
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
                },
                "oee": copy.deepcopy(module["oee"]),
            }

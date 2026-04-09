from __future__ import annotations

import json
import re
from typing import Any


_COLOR_MAP = {
    "KIRMIZI": "red",
    "SARI": "yellow",
    "MAVI": "blue",
    "RED": "red",
    "YELLOW": "yellow",
    "BLUE": "blue",
    "kirmizi": "red",
    "sari": "yellow",
    "mavi": "blue",
    "red": "red",
    "yellow": "yellow",
    "blue": "blue",
    "BOS": "empty",
    "BELIRSIZ": "uncertain",
}


def normalize_token(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return "unknown"
    normalized = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return normalized or "unknown"


def normalize_color(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return "unknown"
    return _COLOR_MAP.get(text, _COLOR_MAP.get(text.upper(), normalize_token(text)))


def normalize_identifier(value: str | None) -> str:
    text = str(value or "").strip()
    if not text or text in {"0", "-"}:
        return ""
    return text


def parse_json_payload(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8", errors="replace")
    if isinstance(payload, str):
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None
    return None


def strip_log_prefix(line: str) -> str:
    text = str(line or "").strip()
    while text.startswith("["):
        match = re.match(r"^\[[^\]]+\]\s*(.*)$", text)
        if match is None:
            break
        text = match.group(1).strip()
    return text


def parse_key_value_line(line: str, *, min_parts: int = 0) -> tuple[list[str], dict[str, str]]:
    parts = [part.strip() for part in line.split("|")]
    fields: dict[str, str] = {}
    for part in parts[min_parts:]:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        fields[key.strip()] = value.strip()
    return parts, fields


def parse_colon_value_line(line: str, *, min_parts: int = 0) -> tuple[list[str], dict[str, str]]:
    parts = [part.strip() for part in line.split("|")]
    fields: dict[str, str] = {}
    for part in parts[min_parts:]:
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        fields[key.strip()] = value.strip()
    return parts, fields


def parse_bool_flag(value: str | None) -> bool:
    return str(value or "").strip() == "1"


def parse_boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def parse_int(value: str | None) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def parse_float(value: str | None) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_status_line(line: str) -> dict[str, Any] | None:
    line = str(line or "").strip()
    if not line.startswith("MEGA|STATUS|"):
        return None
    _, fields = parse_key_value_line(line, min_parts=2)
    return {
        "mode": "auto" if parse_bool_flag(fields.get("AUTO")) else "manual",
        "system_state": normalize_token(fields.get("STATE")),
        "conveyor_state": normalize_token(fields.get("CONVEYOR")),
        "robot_state": normalize_token(fields.get("ROBOT")),
        "last_color": normalize_color(fields.get("LAST")),
        "step_enabled": parse_bool_flag(fields.get("STEP")),
        "queue_depth": parse_int(fields.get("QUEUE")) or 0,
        "stop_request": parse_bool_flag(fields.get("STOP_REQ")),
        "direction": normalize_token(fields.get("DIR")),
        "pwm": parse_int(fields.get("PWM")),
        "travel_ms": parse_int(fields.get("TRAVEL_MS")),
        "limit_22_pressed": parse_bool_flag(fields.get("LIM22")),
        "limit_23_pressed": parse_bool_flag(fields.get("LIM23")),
        "step_hold": parse_bool_flag(fields.get("STEP_HOLD")),
        "step_us": parse_int(fields.get("STEP_US")),
        "raw": fields,
    }


def parse_bridge_status_line(line: str) -> dict[str, Any] | None:
    line = str(line or "").strip()
    if not line.startswith("ESP32|BRIDGE|"):
        return None
    _, fields = parse_key_value_line(line, min_parts=2)
    wifi_connected = parse_bool_flag(fields.get("WIFI"))
    mqtt_connected = parse_bool_flag(fields.get("MQTT"))
    return {
        "state": "online" if wifi_connected and mqtt_connected else "degraded",
        "wifi_connected": wifi_connected,
        "mqtt_connected": mqtt_connected,
        "queue": parse_int(fields.get("QUEUE")) or 0,
        "drop_uart": parse_int(fields.get("DROP_UART")) or 0,
        "drop_pub": parse_int(fields.get("DROP_PUB")) or 0,
        "raw": fields,
    }


def parse_mega_event_from_log(line: str) -> dict[str, Any] | None:
    line = str(line or "").strip()
    if not line.startswith("MEGA|"):
        return None
    parts, fields = parse_key_value_line(line, min_parts=2)
    module_name = parts[1] if len(parts) > 1 else ""
    base = {
        "source": "mega",
        "module_name": module_name,
        "item_id": normalize_identifier(fields.get("ITEM_ID")),
        "measure_id": normalize_identifier(fields.get("MEASURE_ID")),
        "review_required": parse_bool_flag(fields.get("REVIEW")),
        "decision_source": str(fields.get("DECISION_SOURCE") or fields.get("FINAL_SOURCE") or "").strip(),
        "color": normalize_color(fields.get("COLOR") or fields.get("FINAL")),
        "travel_ms": parse_int(fields.get("TRAVEL_MS")),
        "queue_depth": parse_int(fields.get("PENDING") or fields.get("QUEUE")),
        "mega_state": normalize_token(fields.get("STATE")),
        "trigger_source": normalize_token(fields.get("TRIGGER")),
        "reject_reason": normalize_token(fields.get("REASON")),
        "raw": fields,
        "event_type": "",
        "compare_color": None,
    }
    if module_name == "AUTO" and fields.get("QUEUE") == "ENQ":
        base["event_type"] = "queue_enq"
        if base["mega_state"] == "unknown":
            base["mega_state"] = "queue"
        if base["color"] in {"red", "yellow", "blue"}:
            base["compare_color"] = base["color"]
        return base
    if module_name == "AUTO" and fields.get("EVENT") == "ARM_POSITION_REACHED":
        base["event_type"] = "arm_position_reached"
        return base
    if module_name == "AUTO" and fields.get("EVENT") == "PICK_EARLY_REJECT":
        base["event_type"] = "pick_command_rejected"
        return base
    if module_name == "AUTO" and fields.get("EVENT") == "PICKPLACE_DONE":
        base["event_type"] = "pickplace_done"
        return base
    if module_name == "AUTO" and fields.get("EVENT") == "PICKPLACE_RETURN_DONE":
        base["event_type"] = "pickplace_return_done"
        return base
    if module_name == "ROBOT" and fields.get("EVENT") == "RELEASED":
        base["event_type"] = "pick_released"
        return base
    if module_name == "ROBOT" and fields.get("EVENT") == "RETURN_STARTED":
        base["event_type"] = "pick_return_started"
        return base
    if module_name == "ROBOT" and fields.get("EVENT") == "RETURN_REACHED":
        base["event_type"] = "pick_return_reached"
        return base
    if module_name == "TCS3200" and fields.get("STATE") == "MEASURING" and fields.get("FINAL"):
        base["event_type"] = "measurement_decision"
        return base
    return None


def parse_vision_status(payload: Any) -> dict[str, Any] | None:
    data = parse_json_payload(payload)
    if data is None:
        return None
    return {
        "state": normalize_token(str(data.get("state") or "")),
        "fps": parse_float(str(data.get("fps") if data.get("fps") is not None else "")),
        "raw": data,
    }


def parse_vision_tracks(payload: Any) -> dict[str, Any] | None:
    data = parse_json_payload(payload)
    if data is None:
        return None
    return {
        "active_tracks": parse_int(str(data.get("active_tracks") if data.get("active_tracks") is not None else "")) or 0,
        "pending_tracks": parse_int(str(data.get("pending_tracks") if data.get("pending_tracks") is not None else "")) or 0,
        "total_crossings": parse_int(str(data.get("total_crossings") if data.get("total_crossings") is not None else "")) or 0,
        "raw": data,
    }


def parse_vision_heartbeat(payload: Any) -> dict[str, Any] | None:
    data = parse_json_payload(payload)
    if data is None:
        return None
    return {
        "timestamp": str(data.get("timestamp") or "").strip() or None,
        "raw": data,
    }


def parse_vision_event(payload: Any) -> dict[str, Any] | None:
    data = parse_json_payload(payload)
    if data is None:
        return None
    notes: list[str] = []
    if data.get("profile_id"):
        notes.append(f"profile={data['profile_id']}")
    if data.get("frame_index") is not None:
        notes.append(f"frame={data['frame_index']}")
    color = normalize_color(str(data.get("color_name") or data.get("label") or data.get("profile_id") or ""))
    event_type = normalize_token(str(data.get("event") or "vision_event"))
    compare_color = color if event_type == "line_crossed" and color in {"red", "yellow", "blue"} else None
    confidence = parse_float(str(data.get("confidence") if data.get("confidence") is not None else "")) or 0.0
    return {
        "source": "vision",
        "event_type": event_type,
        "color": color,
        "track_id": str(data.get("track_id") or "").strip() or None,
        "item_id": normalize_identifier(data.get("item_id")),
        "measure_id": normalize_identifier(data.get("measure_id")),
        "confidence": confidence,
        "confidence_tier": normalize_token(str(data.get("confidence_tier") or "")) if data.get("confidence_tier") not in (None, "") else None,
        "correlation_status": normalize_token(str(data.get("correlation_status") or "")) if data.get("correlation_status") not in (None, "") else None,
        "late_vision_audit_flag": parse_boolish(data.get("late_vision_audit_flag")),
        "decision_applied": parse_boolish(data.get("decision_applied")),
        "review_required": parse_boolish(data.get("review_required")),
        "vision_observed_at": str(data.get("observed_at") or data.get("timestamp") or "").strip() or None,
        "vision_published_at": str(data.get("published_at") or data.get("timestamp") or "").strip() or None,
        "vision_received_at": str(data.get("received_at") or "").strip() or None,
        "notes": ";".join(notes),
        "compare_color": compare_color,
        "raw": data,
    }


def _tablet_percent(value: str | None) -> float | None:
    parsed = parse_float(value)
    if parsed is None:
        return None
    return parsed * 100 if abs(parsed) <= 1.5 else parsed


def parse_tablet_oee_line(line: str) -> dict[str, Any] | None:
    body = strip_log_prefix(str(line or ""))
    if "|Tablet|OEE|" not in body:
        return None

    parts, fields = parse_colon_value_line(body, min_parts=2)
    if len(parts) < 3:
        return None

    colors: dict[str, dict[str, int]] = {}
    production = {"total": 0, "good": 0, "rework": 0, "scrap": 0}
    for color_name, prefix in (("red", "KIRMIZI"), ("yellow", "SARI"), ("blue", "MAVI")):
        good = parse_int(fields.get(f"{prefix}_S")) or 0
        rework = parse_int(fields.get(f"{prefix}_R")) or 0
        scrap = parse_int(fields.get(f"{prefix}_H")) or 0
        total = good + rework + scrap
        colors[color_name] = {
            "good": good,
            "rework": rework,
            "scrap": scrap,
            "total": total,
        }
        production["total"] += total
        production["good"] += good
        production["rework"] += rework
        production["scrap"] += scrap

    return {
        "oee": _tablet_percent(fields.get("OEE")),
        "availability": _tablet_percent(fields.get("KULL")),
        "performance": _tablet_percent(fields.get("PERF")),
        "quality": _tablet_percent(fields.get("KALITE")),
        "production": production,
        "colors": colors,
        "raw": fields,
        "raw_line": body,
    }


def parse_tablet_fault_line(line: str) -> dict[str, Any] | None:
    body = strip_log_prefix(str(line or ""))
    if not re.search(r"\|Tablet\|Ar[^|]{0,2}za\|", body, flags=re.IGNORECASE) and "|Tablet|Ariza|" not in body:
        return None

    parts, fields = parse_colon_value_line(body, min_parts=2)
    if len(parts) < 3:
        return None

    status = str(fields.get("DURUM") or "").strip()
    return {
        "reason": str(fields.get("NEDEN") or "").strip() or "Bilinmiyor",
        "status": status or "Yok",
        "started_at_text": str(fields.get("BASLANGIC") or "").strip() or None,
        "ended_at_text": str(fields.get("BITIS") or "").strip() or None,
        "duration_min": parse_float(fields.get("SURE_DK")),
        "raw": fields,
        "raw_line": body,
    }

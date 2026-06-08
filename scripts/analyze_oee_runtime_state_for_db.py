from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mes_web.config import AppConfig


JsonObject = dict[str, Any]


def _resolve_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def _read_state_file(path: Path) -> JsonObject:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RuntimeError(f"Runtime state file not found: {path}") from exc
    except OSError as exc:
        raise RuntimeError(f"Runtime state file could not be read: {path} ({exc})") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Runtime state file is not valid JSON: {path} ({exc})") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Runtime state JSON root must be an object: {path}")
    return payload


def _type_name(value: Any) -> str:
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if value is None:
        return "null"
    return type(value).__name__


def _count(value: Any) -> int:
    if isinstance(value, dict | list):
        return len(value)
    return 0


def _top_level_summary(state: JsonObject) -> list[JsonObject]:
    return [
        {
            "key": key,
            "type": _type_name(value),
            "count": _count(value),
        }
        for key, value in sorted(state.items())
    ]


def _dict_at(state: JsonObject, *keys: str) -> JsonObject:
    current: Any = state
    for key in keys:
        if not isinstance(current, dict):
            return {}
        current = current.get(key)
    return current if isinstance(current, dict) else {}


def _list_at(state: JsonObject, *keys: str) -> list[Any]:
    current: Any = state
    for key in keys:
        if not isinstance(current, dict):
            return []
        current = current.get(key)
    return current if isinstance(current, list) else []


def _nonempty_dict(value: Any) -> bool:
    return isinstance(value, dict) and any(v not in (None, "", [], {}) for v in value.values())


def _field_sample(rows: Any, *, limit: int = 20) -> list[str]:
    fields: set[str] = set()
    if isinstance(rows, dict):
        iterable = rows.values()
    elif isinstance(rows, list):
        iterable = rows
    else:
        iterable = []
    for row in iterable:
        if isinstance(row, dict):
            fields.update(str(key) for key in row.keys())
        if len(fields) >= limit:
            break
    return sorted(fields)[:limit]


def _completed_items(items_by_id: JsonObject) -> list[JsonObject]:
    rows: list[JsonObject] = []
    for item in items_by_id.values():
        if not isinstance(item, dict):
            continue
        if item.get("completed_at") or item.get("classification"):
            rows.append(item)
    return rows


def _vision_items(items_by_id: JsonObject) -> list[JsonObject]:
    rows: list[JsonObject] = []
    vision_keys = {
        "vision_color",
        "vision_confidence",
        "vision_track_id",
        "vision_observed_at",
        "vision_published_at",
        "vision_received_at",
        "late_vision_audit_flag",
        "correlation_status",
    }
    for item in items_by_id.values():
        if isinstance(item, dict) and any(item.get(key) not in (None, "") for key in vision_keys):
            rows.append(item)
    return rows


def _active_maintenance_sessions(maintenance: JsonObject) -> list[JsonObject]:
    rows: list[JsonObject] = []
    for key in ("openingSession", "closingSession"):
        session = maintenance.get(key)
        if _nonempty_dict(session):
            enriched = dict(session)
            enriched.setdefault("runtime_session_key", key)
            rows.append(enriched)
    return rows


def _mapping(
    table: str,
    source_json_path: str,
    estimated_count: int,
    natural_key: str,
    payload_fields: list[str],
    missing_or_suspicious_fields: list[str],
    risk_note: str,
) -> JsonObject:
    return {
        "table": table,
        "source_json_path": source_json_path,
        "estimated_count": estimated_count,
        "natural_key_or_external_ref": natural_key,
        "payload_fields": payload_fields,
        "missing_or_suspicious_fields": missing_or_suspicious_fields,
        "risk_note": risk_note,
    }


def _build_mapping_report(state: JsonObject) -> list[JsonObject]:
    work_orders = _dict_at(state, "workOrders")
    orders_by_id = _dict_at(state, "workOrders", "ordersById")
    transition_log = _list_at(state, "workOrders", "transitionLog")
    completion_log = _list_at(state, "workOrders", "completionLog")
    items_by_id = _dict_at(state, "itemsById")
    completed_items = _completed_items(items_by_id)
    fault_history = _list_at(state, "faultHistory")
    active_fault = state.get("activeFault")
    trend = _list_at(state, "trend")
    maintenance = _dict_at(state, "maintenance")
    maintenance_history = _list_at(state, "maintenance", "history")
    active_maintenance = _active_maintenance_sessions(maintenance)
    quality_overrides = _list_at(state, "qualityOverrideLog")
    vision = _dict_at(state, "vision")
    processed_vision_keys = _list_at(state, "processedVisionEventKeys")
    vision_items = _vision_items(items_by_id)
    device_sessions = _dict_at(state, "deviceSessions")

    downtime_count = len(fault_history) + (1 if _nonempty_dict(active_fault) else 0)
    maintenance_count = len(maintenance_history) + len(active_maintenance)
    vision_count = max(len(processed_vision_keys), len(vision_items), 1 if vision else 0)

    return [
        _mapping(
            "mes.work_orders",
            "$.workOrders.ordersById",
            len(orders_by_id),
            "order_id from ordersById key or order_id/orderId field",
            _field_sample(orders_by_id) or ["entire work order object"],
            [] if orders_by_id else ["No work orders found in runtime state."],
            "Good mirror candidate; keep source JSON as payload until final canonical fields are proven.",
        ),
        _mapping(
            "mes.work_order_events",
            "$.workOrders.transitionLog",
            len(transition_log),
            "order_id + event timestamp/reason when present",
            _field_sample(transition_log) or ["transition log row payload"],
            [] if transition_log else ["transitionLog is empty or absent."],
            "Transition reason/timestamp fields may vary by action; preserve full row payload.",
        ),
        _mapping(
            "mes.production_completions",
            "$.workOrders.completionLog and $.itemsById completed rows",
            max(len(completion_log), len(completed_items)),
            "item_id + completed_at, or order_id + item_id when available",
            sorted(set(_field_sample(completion_log) + _field_sample(completed_items))) or ["completion row/item payload"],
            [] if completion_log or completed_items else ["No completionLog rows or completed items found."],
            "CompletionLog and itemsById may overlap; mirror phase must define de-duplication before writes.",
        ),
        _mapping(
            "mes.oee_snapshots",
            "$.trend",
            len(trend),
            "snapshot time + reason",
            _field_sample(trend) or ["trend snapshot payload"],
            [] if trend else ["trend is empty or absent."],
            "Trend is capped runtime history, not a complete historical OEE fact table.",
        ),
        _mapping(
            "mes.downtime_events",
            "$.faultHistory and $.activeFault",
            downtime_count,
            "fault_id when present; otherwise started_at + fault_type_code",
            sorted(set(_field_sample(fault_history) + _field_sample([active_fault] if isinstance(active_fault, dict) else []))) or ["fault payload"],
            [] if downtime_count else ["No faultHistory rows or activeFault found."],
            "activeFault may still be open; mirror logic must distinguish open and closed downtime.",
        ),
        _mapping(
            "mes.maintenance_records",
            "$.maintenance.history, $.maintenance.openingSession, $.maintenance.closingSession",
            maintenance_count,
            "maintenance_row_key or session_id + phase_code",
            sorted(set(_field_sample(maintenance_history) + _field_sample(active_maintenance))) or ["maintenance session payload"],
            [] if maintenance_count else ["No maintenance history or active maintenance sessions found."],
            "Active checklist sessions are mutable runtime state; closed history is safer for mirror first.",
        ),
        _mapping(
            "mes.quality_overrides",
            "$.qualityOverrideLog",
            len(quality_overrides),
            "item_id + recorded_at/applied_at",
            _field_sample(quality_overrides) or ["quality override payload"],
            [] if quality_overrides else ["qualityOverrideLog is empty or absent."],
            "Override rows affect quality metrics; mirror should preserve original classification payload.",
        ),
        _mapping(
            "mes.vision_events",
            "$.processedVisionEventKeys, $.itemsById vision fields, $.vision metrics",
            vision_count,
            "processed vision key, or item_id + vision_track_id + observed_at",
            sorted(set(_field_sample(vision_items) + list(vision.keys())[:20])) or ["vision summary payload"],
            ["Runtime JSON may contain summary/dedupe data rather than every raw vision event."],
            "Not a complete event archive in runtime state; use MQTT/Excel event stream later for fuller mirror.",
        ),
        _mapping(
            "mes.device_sessions",
            "$.deviceSessions",
            len(device_sessions),
            "device_id/session_id dictionary key",
            _field_sample(device_sessions) or ["device session payload"],
            [] if device_sessions else ["deviceSessions is empty or absent."],
            "Session rows can be mutable while a device is active; treat as current-state mirror first.",
        ),
    ]


def _print_human_report(report: JsonObject) -> None:
    print("MES OEE Runtime State DB Dry-Run Analysis")
    print(f"state_file: {report['state_file']}")
    print(f"top_level_key_count: {len(report['top_level_keys'])}")
    print()
    print("Top-level keys:")
    for row in report["top_level_keys"]:
        print(f"- {row['key']}: type={row['type']} count={row['count']}")
    print()
    print("PostgreSQL candidate mapping:")
    for row in report["mappings"]:
        print(f"\n{row['table']}")
        print(f"  source_json_path: {row['source_json_path']}")
        print(f"  estimated_count: {row['estimated_count']}")
        print(f"  natural_key_or_external_ref: {row['natural_key_or_external_ref']}")
        print(f"  payload_fields: {', '.join(row['payload_fields']) if row['payload_fields'] else '(none observed)'}")
        print(
            "  missing_or_suspicious_fields: "
            + (", ".join(row["missing_or_suspicious_fields"]) if row["missing_or_suspicious_fields"] else "(none)")
        )
        print(f"  risk_note: {row['risk_note']}")


def _build_report(state_file: Path, state: JsonObject) -> JsonObject:
    return {
        "state_file": str(state_file),
        "top_level_keys": _top_level_summary(state),
        "mappings": _build_mapping_report(state),
        "writes_to_database": False,
        "writes_to_files": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only dry-run mapper from MES OEE runtime JSON to PostgreSQL candidate tables."
    )
    parser.add_argument(
        "--state-file",
        help="Runtime state JSON path. Defaults to AppConfig.from_env().oee_runtime_state_path.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the dry-run report as JSON to stdout.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = AppConfig.from_env()
    state_file = _resolve_path(args.state_file) if args.state_file else _resolve_path(config.oee_runtime_state_path)

    try:
        state = _read_state_file(state_file)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    report = _build_report(state_file, state)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_human_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

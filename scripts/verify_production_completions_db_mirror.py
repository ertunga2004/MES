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
from mes_web.db.config import build_database_config
from mes_web.db.connection import DatabaseDriverMissingError, database_connection


JsonObject = dict[str, Any]


PRODUCTION_COMPLETIONS_SELECT_SQL = """
SELECT
    external_ref,
    order_id,
    item_id,
    classification,
    completed_at,
    payload
FROM mes.production_completions
ORDER BY external_ref
"""

def extract_order_id(data: JsonObject) -> str | None:
    fields = [
        "orderId", "order_id", "workOrderId", "work_order_id",
        "currentOrderId", "erpOrderId", "sourceOrderId"
    ]
    for f in fields:
        val = data.get(f)
        if val is not None and str(val).strip() not in ["", "None", "null"]:
            return str(val).strip()
    return None

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

def _text(value: Any) -> str:
    return str(value or "").strip()

def _nullable_text(value: Any) -> str | None:
    text = _text(value)
    return text or None

def _json_production_completion_rows(state: JsonObject) -> dict[str, JsonObject]:
    completion_log = state.get("workOrders", {}).get("completionLog", [])
    items_by_id = state.get("itemsById", {})

    completed_items = []
    for item_id, item_data in items_by_id.items():
        if not isinstance(item_data, dict):
            continue
        
        is_completed = False
        if item_data.get("completed_at") or item_data.get("completedAt"):
            is_completed = True
        else:
            cls = str(item_data.get("classification", "")).lower()
            if cls in ["done", "completed", "finished", "good", "scrap", "rework"]:
                is_completed = True
                
        if is_completed:
            if "itemId" not in item_data and "item_id" not in item_data:
                item_data["_extracted_item_id"] = item_id
            completed_items.append(item_data)

    candidate_rows = []
    for row in completion_log:
        if not isinstance(row, dict):
            continue
        candidate_rows.append({"source": "completionLog", "data": row})
        
    for row in completed_items:
        candidate_rows.append({"source": "itemsById", "data": row})

    rows: dict[str, JsonObject] = {}
    seen_natural_keys = set()
    
    for candidate in candidate_rows:
        data = candidate["data"]
        
        item_id = data.get("itemId") or data.get("item_id") or data.get("_extracted_item_id")
        order_id = extract_order_id(data)
        completed_at = data.get("completedAt") or data.get("completed_at")
        classification = data.get("classification")
        
        status = "APPLY_SAFE"
        natural_key = None

        if not order_id:
            status = "SKIPPED_MISSING_ORDER_ID"
        elif not completed_at:
            status = "SKIPPED_MISSING_COMPLETED_AT"
            natural_key = f"{order_id}_{item_id}"
        else:
            natural_key = f"{order_id}_{item_id}"
            
        if natural_key:
            if natural_key in seen_natural_keys:
                status = "SKIPPED_DUPLICATE_KEY"
            else:
                seen_natural_keys.add(natural_key)
                
        if status == "APPLY_SAFE":
            rows[natural_key] = {
                "external_ref": natural_key,
                "order_id": order_id,
                "item_id": item_id,
                "classification": classification,
                "completed_at": completed_at,
                "payload": data,
            }
            
    return rows


def _load_db_rows(app_config: AppConfig) -> tuple[dict[str, JsonObject], list[str]]:
    db_config = build_database_config(app_config)
    if not db_config.enabled:
        raise RuntimeError("DB verification requires MES_WEB_DB_ENABLED=true")

    rows: dict[str, JsonObject] = {}
    duplicates: list[str] = []
    
    with database_connection(db_config) as connection:
        if connection is None:
            raise RuntimeError("DB verification requires an enabled database connection")
        with connection.cursor() as cursor:
            cursor.execute(PRODUCTION_COMPLETIONS_SELECT_SQL)
            for external_ref, order_id, item_id, classification, completed_at, payload in cursor.fetchall():
                ext_ref_str = str(external_ref)
                if ext_ref_str in rows:
                    if ext_ref_str not in duplicates:
                        duplicates.append(ext_ref_str)
                else:
                    rows[ext_ref_str] = {
                        "external_ref": ext_ref_str,
                        "order_id": str(order_id) if order_id is not None else None,
                        "item_id": str(item_id) if item_id is not None else None,
                        "classification": str(classification) if classification is not None else None,
                        "completed_at": str(completed_at) if completed_at is not None else None,
                        "payload": payload,
                    }
    return rows, duplicates


def _compare_rows(json_rows: dict[str, JsonObject], db_rows: dict[str, JsonObject], db_duplicates: list[str]) -> JsonObject:
    json_refs = set(json_rows)
    db_refs = set(db_rows)
    matched = sorted(json_refs & db_refs)
    missing = sorted(json_refs - db_refs)
    extra = sorted(db_refs - json_refs)
    changed: list[JsonObject] = []
    summary = {
        "order_id": {"matched": 0, "changed": 0},
        "item_id": {"matched": 0, "changed": 0},
        "classification": {"matched": 0, "changed": 0},
        "completed_at": {"matched": 0, "changed": 0},
        "payload_presence": {"matched": 0, "changed": 0},
    }

    for ref in matched:
        json_row = json_rows[ref]
        db_row = db_rows[ref]
        differences: list[str] = []
        
        for field in ("order_id", "item_id", "classification"):
            j_val = _nullable_text(json_row.get(field))
            d_val = _nullable_text(db_row.get(field))
            if j_val == d_val:
                summary[field]["matched"] += 1
            else:
                summary[field]["changed"] += 1
                differences.append(field)
                
        j_time = json_row.get("completed_at")
        d_time = db_row.get("completed_at")
        
        if j_time == d_time or (j_time and d_time):
             summary["completed_at"]["matched"] += 1
        else:
             if not j_time and not d_time:
                 summary["completed_at"]["matched"] += 1
             else:
                 summary["completed_at"]["changed"] += 1
                 differences.append("completed_at")

        json_payload_present = bool(json_row.get("payload"))
        db_payload_present = bool(db_row.get("payload"))
        if json_payload_present and db_payload_present:
            summary["payload_presence"]["matched"] += 1
        else:
            summary["payload_presence"]["changed"] += 1
            differences.append("payload_presence")

        if differences:
            changed.append({"external_ref": ref, "fields": differences})

    return {
        "json_apply_safe_count": len(json_rows),
        "db_production_completion_count": len(db_rows) + len(db_duplicates),
        "matched_external_refs": matched,
        "missing_in_db": missing,
        "extra_in_db": extra,
        "duplicate_external_refs": db_duplicates,
        "changed_or_suspicious": changed,
        "field_comparison_summary": summary,
    }


def _print_report(report: JsonObject, state_file: Path) -> None:
    print("MES production completions DB mirror verification")
    print(f"state_file: {state_file}")
    print("db_writes: false")
    print(f"json_apply_safe_count: {report['json_apply_safe_count']}")
    print(f"db_production_completion_count: {report['db_production_completion_count']}")
    
    print(f"matched_external_refs: {len(report['matched_external_refs'])}")
    
    print(f"missing_in_db: {len(report['missing_in_db'])}")
    for ref in report["missing_in_db"]:
        print(f"  - {ref}")
        
    print(f"extra_in_db: {len(report['extra_in_db'])}")
    for ref in report["extra_in_db"]:
        print(f"  - {ref}")
        
    print(f"duplicate_external_refs: {len(report['duplicate_external_refs'])}")
    for ref in report["duplicate_external_refs"]:
        print(f"  - {ref}")
        
    print(f"changed_or_suspicious: {len(report['changed_or_suspicious'])}")
    for item in report["changed_or_suspicious"]:
        print(f"  - {item['external_ref']}: {', '.join(item['fields'])}")
        
    print("field_comparison_summary:")
    for field, counts in report["field_comparison_summary"].items():
        print(f"  {field}: matched={counts['matched']} changed={counts['changed']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only verification for MES runtime production completions against mes.production_completions."
    )
    parser.add_argument("--state-file", required=True, help="Runtime state JSON path.")
    parser.add_argument("--json", action="store_true", help="Print the verification report as JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state_file = _resolve_path(args.state_file)
    app_config = AppConfig.from_env()

    try:
        state = _read_state_file(state_file)
        json_rows = _json_production_completion_rows(state)
        db_rows, db_duplicates = _load_db_rows(app_config)
        report = _compare_rows(json_rows, db_rows, db_duplicates)
    except DatabaseDriverMissingError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Production completion DB mirror verification failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_report(report, state_file)

    if report["missing_in_db"] or report["extra_in_db"] or report["changed_or_suspicious"] or report["duplicate_external_refs"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

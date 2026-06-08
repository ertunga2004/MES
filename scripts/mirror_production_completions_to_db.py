from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mes_web.config import AppConfig
from mes_web.db.config import build_database_config

JsonObject = dict[str, Any]

UPSERT_SQL = """
INSERT INTO mes.production_completions (
    order_id,
    item_id,
    classification,
    completed_at,
    source_system,
    source_file,
    external_ref,
    payload,
    metadata,
    created_at
) VALUES (
    %(order_id)s,
    %(item_id)s,
    %(classification)s,
    %(completed_at)s,
    %(source_system)s,
    %(source_file)s,
    %(external_ref)s,
    %(payload)s,
    %(metadata)s,
    now()
)
"""

UPDATE_SQL = """
UPDATE mes.production_completions SET
    order_id = %(order_id)s,
    item_id = %(item_id)s,
    classification = %(classification)s,
    completed_at = %(completed_at)s,
    source_system = %(source_system)s,
    source_file = %(source_file)s,
    payload = %(payload)s,
    metadata = %(metadata)s
WHERE external_ref = %(external_ref)s
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


def _import_psycopg() -> tuple[Any, Any]:
    try:
        import psycopg
        from psycopg.types.json import Jsonb
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is not installed") from exc
    return psycopg, Jsonb


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dry-run/apply mirror mapping for mes.production_completions"
    )
    parser.add_argument(
        "--state-file",
        required=True,
        help="Runtime state JSON path",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write to mes.production_completions. Requires MES_WEB_DB_ENABLED=true.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    app_config = AppConfig.from_env()
    state_file = _resolve_path(args.state_file)

    try:
        state = _read_state_file(state_file)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

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

    mapped_rows = []
    missing_order_id_count = 0
    missing_completed_at_count = 0
    missing_stable_key_count = 0
    duplicate_candidate_count = 0
    apply_safe_count = 0
    apply_unsafe_count = 0
    
    seen_natural_keys = set()
    
    for candidate in candidate_rows:
        data = candidate["data"]
        source_origin = candidate["source"]
        
        item_id = data.get("itemId") or data.get("item_id") or data.get("_extracted_item_id")
        order_id = extract_order_id(data)
        completed_at = data.get("completedAt") or data.get("completed_at")
        classification = data.get("classification")
        
        status = "APPLY_SAFE"
        natural_key = None

        if not order_id:
            missing_order_id_count += 1
            missing_stable_key_count += 1
            status = "SKIPPED_MISSING_ORDER_ID"
        elif not completed_at:
            missing_completed_at_count += 1
            status = "SKIPPED_MISSING_COMPLETED_AT"
            natural_key = f"{order_id}_{item_id}"
        else:
            natural_key = f"{order_id}_{item_id}"
            
        if natural_key:
            if natural_key in seen_natural_keys:
                duplicate_candidate_count += 1
                status = "SKIPPED_DUPLICATE_KEY"
            else:
                seen_natural_keys.add(natural_key)
                
        if status == "APPLY_SAFE":
            apply_safe_count += 1
            mapped = {
                "order_id": order_id,
                "item_id": item_id,
                "classification": classification,
                "completed_at": completed_at,
                "source_system": "mes_web",
                "source_file": None,
                "external_ref": natural_key,
                "payload": data,
                "metadata": {
                    "source_path": source_origin,
                    "inventoryAction": data.get("inventoryAction"),
                    "work_order_match_key": data.get("work_order_match_key"),
                    "dry_run_status": status,
                    "mirrored_by": "scripts/mirror_production_completions_to_db.py",
                    "mapped_at": datetime.now(timezone.utc).isoformat(),
                }
            }
            mapped_rows.append(mapped)
        else:
            apply_unsafe_count += 1

    print("--- Production Completions Mirror Mapping ---")
    print(f"candidate_row_count: {len(candidate_rows)}")
    print(f"apply_safe_count: {apply_safe_count}")
    print(f"apply_unsafe_count: {apply_unsafe_count}")
    print(f"missing_order_id_count: {missing_order_id_count}")
    print(f"missing_completed_at_count: {missing_completed_at_count}")
    print(f"duplicate_candidate_count: {duplicate_candidate_count}")

    if not args.apply:
        print("db_writes: False")
        print("inserted: 0")
        print("updated: 0")
        return 0

    db_config = build_database_config(app_config)
    if not db_config.enabled:
        print("Error: --apply requires MES_WEB_DB_ENABLED=true; no DB connection was opened.", file=sys.stderr)
        return 1

    if not mapped_rows:
        print("No APPLY_SAFE production completions found; nothing to apply.")
        print("db_writes: False")
        return 0

    psycopg, Jsonb = _import_psycopg()
    existing_refs: set[str] = set()
    inserted = 0
    updated = 0

    with psycopg.connect(**db_config.connection_kwargs()) as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT external_ref FROM mes.production_completions")
                existing_refs = {str(row[0]) for row in cursor.fetchall()}
                for row in mapped_rows:
                    params = dict(row)
                    params["payload"] = Jsonb(row["payload"])
                    params["metadata"] = Jsonb(row["metadata"])
                    if row["external_ref"] in existing_refs:
                        cursor.execute(UPDATE_SQL, params)
                        updated += 1
                    else:
                        cursor.execute(UPSERT_SQL, params)
                        inserted += 1
                        existing_refs.add(row["external_ref"])
            connection.commit()
        except Exception as exc:
            connection.rollback()
            print(f"Production completion mirror apply failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1

    print("db_writes: True")
    print(f"inserted: {inserted}")
    print(f"updated: {updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

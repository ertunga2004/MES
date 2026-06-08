import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True

def extract_order_id(data):
    fields = [
        "orderId", "order_id", "workOrderId", "work_order_id",
        "currentOrderId", "erpOrderId", "sourceOrderId"
    ]
    for f in fields:
        val = data.get(f)
        if val is not None and str(val).strip() not in ["", "None", "null"]:
            return str(val).strip()
    return None

def main():
    parser = argparse.ArgumentParser(description="Dry-run mirror mapping for mes.production_completions")
    parser.add_argument("--state-file", required=True, help="Path to oee_runtime_state.json")
    args = parser.parse_args()

    state_path = Path(args.state_file)
    if not state_path.exists():
        print(f"Error: State file not found: {state_path}")
        sys.exit(1)

    try:
        with state_path.open("r", encoding="utf-8") as f:
            state = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON format in state file: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: Unexpected error reading state file: {e}")
        sys.exit(1)

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

    print("--- Dry-Run Production Completions Mirror Mapping ---")
    
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
    warnings = []
    
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
            warnings.append(f"Warning: {status} for item_id '{item_id}' (Source: {source_origin}). Rows with missing order_id are not safe for DB apply.")
            warnings.append(f"No external_ref is generated from None/null order_id.")
        elif not completed_at:
            missing_completed_at_count += 1
            status = "SKIPPED_MISSING_COMPLETED_AT"
            warnings.append(f"Warning: {status} for order_id '{order_id}', item_id '{item_id}' (Source: {source_origin}).")
            natural_key = f"{order_id}_{item_id}"
        else:
            natural_key = f"{order_id}_{item_id}"
            
        if natural_key:
            if natural_key in seen_natural_keys:
                duplicate_candidate_count += 1
                status = "SKIPPED_DUPLICATE_KEY"
                warnings.append(f"Overlap/Duplicate Risk: {status} for natural key '{natural_key}' (Source: {source_origin}).")
            else:
                seen_natural_keys.add(natural_key)
                
        if status == "APPLY_SAFE":
            apply_safe_count += 1
        else:
            apply_unsafe_count += 1
            
        mapped = {
            "order_id": order_id,
            "item_id": item_id,
            "classification": classification,
            "completed_at": completed_at,
            "source_system": "mes_web",
            "source_file": None,
            "external_ref": natural_key if status != "SKIPPED_MISSING_ORDER_ID" else None,
            "payload": data,
            "metadata": {
                "dry_run_mapped_at": datetime.now(timezone.utc).isoformat(),
                "original_source": source_origin,
                "status": status
            }
        }
        mapped_rows.append(mapped)

    print(f"\nExtracted Candidates: {len(candidate_rows)}")
    for sample in mapped_rows:
        print(f"\nSample Mapping (Status: {sample['metadata']['status']}, Natural Key: {sample['external_ref']}):")
        for k, v in sample.items():
            if k in ["payload", "metadata"]:
                print(f"  {k}: (JSON Data) -> source: {sample['metadata']['original_source']}")
            else:
                print(f"  {k}: {v}")
        break  # Just print the first one

    print("\n--- Mapping Warnings ---")
    if not warnings:
        print("None")
    else:
        for w in warnings:
            print(w)

    print("\n--- Summary ---")
    summary = {
        "completion_log_count": len(completion_log),
        "completed_items_count": len(completed_items),
        "candidate_row_count": len(candidate_rows),
        "mapped_row_count": len(mapped_rows),
        "missing_order_id_count": missing_order_id_count,
        "missing_completed_at_count": missing_completed_at_count,
        "missing_stable_key_count": missing_stable_key_count,
        "duplicate_candidate_count": duplicate_candidate_count,
        "apply_safe_count": apply_safe_count,
        "apply_unsafe_count": apply_unsafe_count,
        "db_writes": False
    }
    
    for k, v in summary.items():
        print(f"{k}: {v}")

    sys.exit(0)

if __name__ == "__main__":
    main()

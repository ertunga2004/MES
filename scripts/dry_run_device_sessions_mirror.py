import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

sys.dont_write_bytecode = True

def main():
    parser = argparse.ArgumentParser(description="Dry-run mirror mapping for mes.device_sessions")
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

    device_sessions = state.get("deviceSessions", {})
    if not device_sessions:
        print("Note: 'deviceSessions' key not found or empty in runtime state. Nothing to map.")
        # Proceed to print the summary with 0s
        device_sessions = {}

    db_columns = {
        "device_id", "device_role", "operator_id", "started_at", "ended_at",
        "source_system", "source_file", "external_ref", "payload", "metadata"
    }

    mapped_rows = []
    missing_stable_key_count = 0
    duplicate_key_count = 0
    active_session_count = 0
    ended_session_count = 0
    
    seen_natural_keys = set()
    warnings = ["Note: 'lastSeenAt' is volatile and is STRICTLY EXCLUDED from natural key generation."]

    print("--- Dry-Run Device Sessions Mirror Mapping ---")

    for session_key, session_data in device_sessions.items():
        if not isinstance(session_data, dict):
            continue

        device_id = session_data.get("deviceId") or session_key
        session_id = session_data.get("sessionId")
        started_at = session_data.get("connectedAt") or session_data.get("startedAt")
        
        # Natural key logic
        if session_id:
            natural_key = session_id
        elif device_id and started_at:
            natural_key = f"{device_id}_{started_at}"
        else:
            missing_stable_key_count += 1
            natural_key = None

        if natural_key:
            if natural_key in seen_natural_keys:
                duplicate_key_count += 1
            seen_natural_keys.add(natural_key)
        else:
            warnings.append(f"Warning: Missing stable key for device_id '{device_id}'. Record will be SKIPPED during DB apply.")
            natural_key = "skipped_missing_stable_key"

        ended_at = session_data.get("endedAt") or session_data.get("disconnectedAt")
        if ended_at:
            ended_session_count += 1
            status = "ended"
        else:
            active_session_count += 1
            status = "active"

        # Map to PostgreSQL mes.device_sessions schema
        mapped = {
            "source_system": "mes_web",
            "external_ref": natural_key,
            "device_id": device_id,
            "device_role": session_data.get("deviceRole") or session_data.get("role"),
            "operator_id": session_data.get("operatorId") or session_data.get("operatorCode"),
            "started_at": started_at,
            "ended_at": ended_at,
            "payload": session_data,
            "metadata": {
                "dry_run_mapped_at": datetime.now(timezone.utc).isoformat(),
                "original_session_key": session_key
            }
        }

        # Check for unmapped fields requested by user but missing in DB schema
        unmapped_fields = {}
        if session_data.get("boundStationId") or session_data.get("stationId"):
            unmapped_fields["station_id"] = session_data.get("boundStationId") or session_data.get("stationId")
            warnings.append(f"Warning: 'boundStationId'/'stationId' found for {natural_key} but no column exists in DB schema.")
            
        if "lastSeenAt" in session_data:
            unmapped_fields["last_seen_at"] = session_data.get("lastSeenAt")
            warnings.append(f"Warning: 'lastSeenAt' found for {natural_key} but no column exists in DB schema.")

        if unmapped_fields:
            mapped["metadata"]["unmapped_fields"] = unmapped_fields
            
        mapped["metadata"]["status"] = status

        mapped_rows.append(mapped)

        print(f"\nExtracted Session -> Natural Key: {natural_key}")
        for k, v in mapped.items():
            if k in ["payload", "metadata"]:
                print(f"  {k}: (JSON Data)")
            else:
                print(f"  {k}: {v}")

    print("\n--- Mapping Warnings ---")
    if not warnings:
        print("None")
    else:
        for w in set(warnings):
            print(w)

    print("\n--- Summary ---")
    summary = {
        "state_file": str(state_path),
        "device_session_count": len(device_sessions),
        "mapped_row_count": len(mapped_rows),
        "missing_stable_key_count": missing_stable_key_count,
        "duplicate_key_count": duplicate_key_count,
        "active_session_count": active_session_count,
        "ended_session_count": ended_session_count,
        "db_writes": False
    }
    
    for k, v in summary.items():
        print(f"{k}: {v}")

    sys.exit(0)

if __name__ == "__main__":
    main()

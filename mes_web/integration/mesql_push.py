from __future__ import annotations

from typing import Any

from ..config import AppConfig
from ..db.mesql_v2 import JsonObject, mark_outbox_error, mark_outbox_pushed, pending_outbox_events
from .mesql_client import MesqlClient


def _request_payload(event_payload: JsonObject) -> JsonObject:
    request = event_payload.get("mesql_request")
    return dict(request) if isinstance(request, dict) else {}


def push_mesql_outbox(
    config: AppConfig,
    *,
    limit: int = 50,
    dry_run: bool = False,
    client: MesqlClient | None = None,
) -> JsonObject:
    events = pending_outbox_events(config, limit=limit)
    mesql_client = client or MesqlClient.from_config(config)
    pushed: list[JsonObject] = []
    failed: list[JsonObject] = []
    dry_run_payloads: list[JsonObject] = []

    for event in events:
        payload = _request_payload(event.payload)
        row = {
            "outbox_id": event.outbox_id,
            "event_type": event.event_type,
            "dedupe_key": event.dedupe_key,
            "payload": payload,
        }
        if dry_run:
            dry_run_payloads.append(row)
            continue
        try:
            if event.event_type == "operation_started":
                response = mesql_client.start_operation(payload)
            elif event.event_type == "operation_completed":
                response = mesql_client.complete_operation(payload)
            else:
                raise RuntimeError(f"UNSUPPORTED_OUTBOX_EVENT: {event.event_type}")
            mark_outbox_pushed(config, event.outbox_id)
            pushed.append({**row, "response": response})
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            mark_outbox_error(config, event.outbox_id, message)
            failed.append({**row, "error": message})

    return {
        "status": "ok" if not failed else "partial_error",
        "dry_run": dry_run,
        "read_count": len(events),
        "pushed_count": len(pushed),
        "failed_count": len(failed),
        "dry_run_payloads": dry_run_payloads,
        "pushed": pushed,
        "failed": failed,
    }

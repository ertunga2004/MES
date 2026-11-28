from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

TAPES_PER_BOX = 2

def empty_cutting_workflow() -> dict[str, Any]:
    return {"batches": {}, "receipts": {}, "protocol4": {}, "tabletRuns": {}}


def cutting_batch(state: dict[str, Any], order_id: str, order_key: str) -> dict[str, Any]:
    return state["cuttingWorkflow"]["batches"].get(order_id, {}).get(order_key, {})


def apply_cutting_action(state: dict[str, Any], progress: dict[str, Any] | None, request_id: str, action: dict[str, Any]) -> bool:
    """Apply an action while the caller holds the runtime file lock. Return whether it was already saved."""
    workflow = state["cuttingWorkflow"]
    receipt = workflow["receipts"].get(request_id)
    if receipt is not None:
        previous_action = dict(receipt["action"])
        if previous_action.get("operation") == "cut" and previous_action.get("lot_id") == "":
            previous_action.pop("lot_id")
        if previous_action != action:
            raise ValueError("CUTTING_REQUEST_CONFLICT")
        return True

    order_id, order_key = action["order_id"], action["order_key"]
    if (
        not progress or (order_id, order_key) != (progress["order_id"], progress["order_key"])
        or not progress["cutting"]["order_open"]
    ):
        raise ValueError("CUTTING_ORDER_CHANGED")
    cutting = progress["cutting"]
    if cutting["legacy_blocked"]:
        raise ValueError("CUTTING_LEGACY_ORDER")
    if not 0 < action["quantity"] <= cutting["target_tapes"] - cutting["cut_tapes"]:
        raise ValueError("CUTTING_QUANTITY_UNAVAILABLE")
    cut_tapes = cutting["cut_tapes"] + action["quantity"]
    workflow["batches"].setdefault(order_id, {})[order_key] = {"cut_tapes": cut_tapes}
    station_order = cutting.get("station_order") or {}
    workflow["receipts"][request_id] = {
        "action": action, "cut_tapes": cut_tapes,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "station_order_id": station_order.get("station_order_id", ""),
        "unit": station_order.get("unit", "adet"),
    }
    return False

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


def empty_cutting_workflow() -> dict[str, Any]:
    return {"batches": {}, "receipts": {}}


def cutting_batch(state: dict[str, Any], order_id: str, order_key: str) -> dict[str, Any]:
    return state["cuttingWorkflow"]["batches"].get(order_id, {}).get(order_key, {})


def waiting_lot(state: dict[str, Any]) -> dict[str, Any] | None:
    for order_id, versions in state["cuttingWorkflow"]["batches"].items():
        for order_key, batch in versions.items():
            if batch["status"] == "parked":
                return {**batch, "order_id": order_id, "order_key": order_key}
    return None


def apply_cutting_action(state: dict[str, Any], progress: dict[str, Any] | None, request_id: str, action: dict[str, Any]) -> bool:
    """Apply an action while the caller holds the runtime file lock. Return whether it was already saved."""
    workflow = state["cuttingWorkflow"]
    receipt = workflow["receipts"].get(request_id)
    if receipt is not None:
        if receipt["action"] != action:
            raise ValueError("CUTTING_REQUEST_CONFLICT")
        return True

    order_id, order_key = action["order_id"], action["order_key"]
    operation = action["operation"]
    batch = cutting_batch(state, order_id, order_key)
    status = batch.get("status", "cutting")
    lot_id = batch.get("lot_id", "")
    cut_qty = batch.get("cut_qty", 0)

    if operation == "withdraw":
        if status != "parked" or action["lot_id"] != lot_id:
            raise ValueError("CUTTING_WRONG_LOT")
    elif (
        not progress or (order_id, order_key) != (progress["order_id"], progress["order_key"])
        or not progress["cutting"]["order_open"]
    ):
        raise ValueError("CUTTING_ORDER_CHANGED")

    if operation == "cut":
        if status != "cutting" or not 0 < action["quantity"] <= progress["target_qty"] - cut_qty:
            raise ValueError("CUTTING_QUANTITY_UNAVAILABLE")
        cut_qty += action["quantity"]
        lot_id = lot_id or f"P-{uuid.uuid4().hex[:12].upper()}"
    elif operation == "park":
        if status != "cutting" or cut_qty != progress["target_qty"]:
            raise ValueError("CUTTING_LOT_INCOMPLETE")
        if waiting_lot(state) is not None:
            raise ValueError("CUTTING_WIP_OCCUPIED")
    elif operation == "pickup":
        if status != "parked" or action["lot_id"] != lot_id:
            raise ValueError("CUTTING_WRONG_LOT")
        if cut_qty != progress["target_qty"]:
            raise ValueError("CUTTING_LOT_INCOMPLETE")

    new_status = {"cut": "cutting", "park": "parked", "pickup": "picked_up", "withdraw": "cutting"}[operation]
    workflow["batches"].setdefault(order_id, {})[order_key] = {
        "status": new_status, "lot_id": lot_id, "cut_qty": cut_qty,
    }
    workflow["receipts"][request_id] = {
        "action": action, "lot_id": lot_id, "cut_qty": cut_qty, "status": new_status,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    return False

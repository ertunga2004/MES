from __future__ import annotations

from typing import Any

from .cutting_workflow import TAPES_PER_BOX, cutting_batch

def manual_coating_order_key(order: dict[str, Any]) -> str:
    return order.get("manualCoatingKey") or f"legacy:{order['queuedAt']}"


def manual_coating_progress(state: dict[str, Any], *, cutting_enabled: bool = False) -> dict[str, Any] | None:
    work_orders = state["workOrders"]
    order_id = work_orders["activeOrderId"]
    order = work_orders["ordersById"].get(order_id)
    if not order:
        return None

    order_key = manual_coating_order_key(order)
    target = order["quantity"]
    completed = sum(
        record["quantity"] for record in state["manualCoatingRecords"].values()
        if record["order_id"] == order_id and record["order_key"] == order_key
    )
    complete = target > 0 and completed >= target
    active = order["status"] == "active"
    unit_supported = order["unit"].strip().casefold() in {"", "adet"}
    progress = {
        "order_id": order_id,
        "order_key": order_key,
        "target_qty": target,
        "completed_qty": completed,
        "remaining_qty": max(0, target - completed),
        "complete": complete,
        "unit_supported": unit_supported,
        "awaiting_handoff": active and complete and order["productionQty"] == 0,
        "can_record": active and unit_supported and completed < target,
    }
    batch = cutting_batch(state, order_id, order_key)
    if cutting_enabled or "cut_tapes" in batch:
        legacy_blocked = "cut_tapes" not in batch and (bool(batch) or completed > 0)
        cut_tapes = batch.get("cut_tapes", 0)
        available_boxes = max(0, min(target, cut_tapes // TAPES_PER_BOX) - completed)
        progress["cutting"] = {
            "target_tapes": target * TAPES_PER_BOX,
            "cut_tapes": cut_tapes,
            "unpaired_tapes": cut_tapes % TAPES_PER_BOX,
            "available_boxes": available_boxes,
            "order_open": active and unit_supported and target > 0,
            "legacy_blocked": legacy_blocked,
        }
        progress["can_record"] &= not legacy_blocked and available_boxes > 0
        progress["remaining_qty"] = available_boxes
    return progress

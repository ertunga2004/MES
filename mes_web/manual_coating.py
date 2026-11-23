from __future__ import annotations

from typing import Any

from .cutting_workflow import cutting_batch

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
    if cutting_enabled:
        batch = cutting_batch(state, order_id, order_key)
        status = batch.get("status", "cutting")
        cut_qty = batch.get("cut_qty", 0)
        progress["cutting"] = {
            "status": status, "cut_qty": cut_qty, "lot_id": batch.get("lot_id", ""),
            "order_open": active and unit_supported and target > 0,
        }
        progress["can_record"] &= status == "picked_up" and completed < cut_qty
        progress["remaining_qty"] = max(0, min(target, cut_qty) - completed)
    return progress

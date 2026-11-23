from __future__ import annotations

from typing import Any


def manual_coating_order_key(order: dict[str, Any]) -> str:
    return order.get("manualCoatingKey") or f"legacy:{order['queuedAt']}"


def manual_coating_progress(state: dict[str, Any]) -> dict[str, Any] | None:
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
    return {
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

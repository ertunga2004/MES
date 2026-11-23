from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .manual_coating import manual_coating_order_key


PENDING_STATUSES = {"waiting_entry", "confirm_entry", "needs_review"}


def pending_handoff(state: dict[str, Any]) -> dict[str, Any] | None:
    return next((row for row in state["conveyorHandoffs"].values() if row["status"] in PENDING_STATUSES), None)


def handoff_view(state: dict[str, Any], progress: dict[str, Any] | None) -> dict[str, Any]:
    records = state["conveyorHandoffs"].values()
    current = [row for row in records if progress and (row["order_id"], row["order_key"]) == (progress["order_id"], progress["order_key"])]
    pending = pending_handoff(state)
    ready = max(0, (progress["completed_qty"] if progress else 0) - sum(row["status"] != "cancelled" for row in current))
    order = state["workOrders"]["ordersById"].get(progress["order_id"]) if progress else None
    order_open = bool(order and order["status"] == "active" and progress["unit_supported"])
    return {"ready_qty": ready, "pending": pending,
            "latest": max(current if progress else records, key=lambda row: row["started_at"], default=None),
            "shift_active": bool(state["shift"]["active"]),
            "can_start": bool(ready and order_open and not pending and state["shift"]["active"])}


def start_handoff(state: dict[str, Any], progress: dict[str, Any] | None, request_id: str, order_id: str,
                  order_key: str, operator: str) -> bool:
    records = state["conveyorHandoffs"]
    previous = records.get(request_id)
    if previous is not None:
        if (previous["order_id"], previous["order_key"], previous["operator"]) != (order_id, order_key, operator):
            raise ValueError("HANDOFF_REQUEST_CONFLICT")
        return False
    if not progress or (progress["order_id"], progress["order_key"]) != (order_id, order_key):
        raise ValueError("HANDOFF_ORDER_CHANGED")
    order = state["workOrders"]["ordersById"][order_id]
    if order["status"] != "active" or not progress["unit_supported"]:
        raise ValueError("HANDOFF_ORDER_CHANGED")
    if pending_handoff(state):
        raise ValueError("HANDOFF_ALREADY_OPEN")
    if not state["shift"]["active"]:
        raise ValueError("HANDOFF_SHIFT_REQUIRED")
    if not handoff_view(state, progress)["ready_qty"]:
        raise ValueError("HANDOFF_NO_BOX")
    records[request_id] = {"id": request_id, "order_id": order_id, "order_key": order_key,
                           "operator": operator, "started_at": datetime.now(timezone.utc).isoformat(),
                           "status": "waiting_entry", "candidate": None}
    return True


def observe_handoff_entry(state: dict[str, Any], item: dict[str, Any], detected: datetime, received: datetime) -> None:
    handoff = pending_handoff(state)
    if not handoff or handoff["status"] == "needs_review":
        return
    seen_at = min(value.astimezone(timezone.utc) for value in (detected, received))
    if seen_at < datetime.fromisoformat(handoff["started_at"]):
        return
    work_orders = state["workOrders"]
    current_id = work_orders["activeOrderId"]
    order = work_orders["ordersById"].get(current_id)
    reused_without_measurement = not item.get("measured_at") and any(
        (candidate["item_id"], candidate["measure_id"]) == (item["item_id"], item["measure_id"])
        for row in state["conveyorHandoffs"].values() if (candidate := row.get("candidate"))
    )
    if (handoff["candidate"] or not item["measure_id"] or not order or order["status"] != "active"
        or not state["shift"]["active"] or reused_without_measurement
        or (current_id, manual_coating_order_key(order)) != (handoff["order_id"], handoff["order_key"])):
        handoff["status"] = "needs_review"
        return
    handoff["candidate"] = {"item_id": item["item_id"], "measure_id": item["measure_id"],
                            "color": item["sensor_color"], "queued_at": item["queued_at"]}
    handoff["status"] = "confirm_entry"
    item["coating_handoff_id"] = handoff["id"]


def observe_handoff_completion(state: dict[str, Any], item: dict[str, Any]) -> None:
    handoff = state["conveyorHandoffs"].get(item.get("coating_handoff_id", ""))
    if not handoff or handoff["status"] not in {"confirm_entry", "on_conveyor"}:
        return
    candidate = handoff["candidate"]
    if (candidate["item_id"], candidate["measure_id"]) != (item["item_id"], item["measure_id"]):
        handoff["status"] = "order_mismatch" if handoff["status"] == "on_conveyor" else "needs_review"
        return
    handoff["completed_at"] = item["completed_at"]
    handoff["line_order_id"] = item.get("work_order_id") or ""
    order = state["workOrders"]["ordersById"].get(handoff["line_order_id"])
    handoff["line_order_key"] = manual_coating_order_key(order) if order else ""
    if handoff["status"] == "on_conveyor":
        handoff["status"] = _completion_status(handoff)


def _completion_status(handoff: dict[str, Any]) -> str:
    return "completed" if (handoff["line_order_id"], handoff["line_order_key"]) == (handoff["order_id"], handoff["order_key"]) else "order_mismatch"


def resolve_handoff(state: dict[str, Any], handoff_id: str, action: str, item_id: str, measure_id: str) -> bool:
    handoff = state["conveyorHandoffs"].get(handoff_id)
    if not handoff:
        raise ValueError("HANDOFF_NOT_FOUND")
    status = handoff["status"]
    if action == "close":
        if status in {"cancelled", "unresolved"}:
            return False
        if status not in PENDING_STATUSES:
            raise ValueError("HANDOFF_CHANGED")
        handoff["status"] = "cancelled" if status == "waiting_entry" else "unresolved"
        return True
    candidate = handoff["candidate"]
    if not candidate or (candidate["item_id"], candidate["measure_id"]) != (item_id, measure_id):
        raise ValueError("HANDOFF_CHANGED")
    if status in {"on_conveyor", "completed", "order_mismatch"}:
        return False
    if status != "confirm_entry":
        raise ValueError("HANDOFF_CHANGED")
    handoff["status"] = _completion_status(handoff) if handoff.get("completed_at") else "on_conveyor"
    return True

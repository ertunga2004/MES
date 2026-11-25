"""Adapt the modular workstations to the shared MES runtime and conveyor records."""

from __future__ import annotations

from datetime import datetime, timezone
from time import time

from .conveyor_handoff import PENDING_STATUSES, pending_handoff, resolve_handoff, start_handoff
from .cutting_workflow import TAPES_PER_BOX
from .employee_actions import ACTIONS, apply_action
from .employee_planning import planning_snapshot
from .employee_rules import COLORS, record_demo_exit, require
from .manual_coating import manual_coating_order_key, manual_coating_progress
from .parsers import normalize_color


def now_ms() -> int:
    return int(time() * 1000)


def stamp_ms(value: str | None) -> int | None:
    if not value:
        return None
    try:
        stamp = datetime.fromisoformat(value)
        return int(stamp.timestamp() * 1000)
    except (TypeError, ValueError, OverflowError):
        return None


def initial_flow() -> dict:
    return {
        "revision": 0, "nextId": 1, "activeBox": None, "activeOrder": None, "items": [],
        "shift": {"active": False}, "stationShifts": {}, "orderDetails": {}, "instruction": None,
        "instructionHistory": [], "tape": dict.fromkeys(COLORS, "ok"), "alerts": [], "events": [],
        "activity": None, "activities": [], "lineStops": [], "logs": [], "settings": {"cleaningMinutes": 10},
        "dailyTargets": {}, "qualityChanges": [], "receipts": {},
    }


def project_orders(state: dict, flow: dict) -> list[dict]:
    book = state["workOrders"]
    source = book["ordersById"]
    ordered = list(dict.fromkeys([*book.get("queue", []), *source]))
    orders = []
    for index, order_id in enumerate(ordered, 1):
        order = source.get(order_id)
        if not order:
            continue
        quantities = dict.fromkeys(COLORS, 0)
        for line in order["requirements"]:
            color = normalize_color(line.get("color"))
            if color in quantities:
                quantities[color] += line["quantity"]
        if not any(quantities.values()) or str(order.get("unit", "")).strip().casefold() not in {"", "adet"}:
            continue
        key = manual_coating_order_key(order)
        details = flow["orderDetails"].get(key, {})
        orders.append({
            "id": order_id, "key": key, "requirements": quantities, "status": order["status"],
            "customer": order.get("customerName") or order.get("customer") or order.get("stockName") or "",
            "priority": "urgent" if order.get("priority") in {"urgent", "high"} else "normal",
            "rank": index, **details,
        })
    return sorted(orders, key=lambda order: order["rank"])


def reconcile_items(state: dict, flow: dict, now: int) -> None:
    if flow["mode"] == "demo":
        for item in flow["items"]:
            if item["stage"] == "transit" and now - item["deliveredAt"] >= 3_000:
                record_demo_exit(flow, item, now)
        return
    handoffs = state["conveyorHandoffs"]
    runtime_items = {}
    for item in state["itemsById"].values():
        if item.get("coating_handoff_id") and item.get("completed_at"):
            runtime_items[item["coating_handoff_id"]] = item
    linked = {item.get("handoffId"): item for item in flow["items"]}
    for handoff_id, handoff in handoffs.items():
        item = linked.get(handoff_id)
        produced = runtime_items.get(handoff_id)
        status = handoff["status"]
        if item is None and status == "completed" and produced:
            candidate = handoff.get("candidate") or {}
            color = normalize_color(produced.get("final_color") or candidate.get("color"))
            if color not in COLORS:
                continue
            item = {
                "id": "HAT-" + handoff_id, "orderId": handoff["order_id"], "orderKey": handoff["order_key"],
                "color": color, "quality": "good", "stage": "transit", "handoffId": handoff_id,
                "operator": handoff["operator"], "deliveredAt": stamp_ms(handoff["started_at"]),
            }
            flow["items"].append(item)
        if item is None or item["stage"] == "packed":
            continue
        if status in {"unresolved", "cancelled", "order_mismatch"}:
            item["stage"] = "review"
        elif status == "completed" and produced:
            color = normalize_color(produced.get("final_color"))
            classification = str(produced.get("classification") or "").upper()
            if color != item["color"] or classification != "GOOD" or produced.get("review_required"):
                item["stage"] = "review"
            else:
                item.update(stage="exited", exitedAt=stamp_ms(handoff.get("completed_at")))


def load_flow(state: dict, config, now: int) -> dict:
    mode = "demo" if config.employee_simulation_enabled else "live"
    flow = state["employeeStations"].get(mode) or initial_flow()
    flow["mode"] = mode
    flow["orders"] = project_orders(state, flow)
    by_id = {row["id"]: row for row in flow["orders"]}
    canonical = state["workOrders"]["activeOrderId"]
    if flow["activeBox"]:
        flow["activeOrder"] = flow["activeBox"]["orderId"]
    elif mode == "live" or flow["activeOrder"] not in by_id:
        flow["activeOrder"] = canonical if canonical in by_id else None
    reconcile_items(state, flow, now)
    return flow


def taping_block(state, config, mode):
    if mode == "demo":
        return ""
    if not config.conveyor_handoff_enabled:
        return "Konveyör teslimi bu sunucuda kapalı."
    if not state["shift"]["active"]:
        return "Konveyör hat vardiyası bekleniyor."
    if pending_handoff(state):
        return "Önce açık konveyör teslimini sonuçlandır."
    progress = manual_coating_progress(state, cutting_enabled=config.cutting_workflow_enabled)
    if not progress or not progress["can_record"]:
        return "Aktif iş emri ve bu kutu için kullanılabilir bant bekleniyor."
    return ""


def finish_live_box(state: dict, flow: dict, config, box: dict) -> None:
    progress = manual_coating_progress(state, cutting_enabled=config.cutting_workflow_enabled)
    require(progress and (progress["order_id"], progress["order_key"]) == (box["orderId"], box["orderKey"]),
            "Ortak MES'teki aktif iş emri değişti.", 409)
    require(config.conveyor_handoff_enabled, "Konveyör teslimi bu sunucuda açık değil.", 409)
    require(progress["can_record"] and progress["remaining_qty"] >= 1, "Bu kutu için yeterli kesilmiş bant yok.", 409)
    handoff_id = "station-" + box["id"]
    quantity = {"order_id": box["orderId"], "order_key": box["orderKey"], "operator": box["operator"], "quantity": 1}
    if "cutting" in progress:
        quantity["tapes_used"] = TAPES_PER_BOX
    state["manualCoatingRecords"][handoff_id] = {**quantity, "recorded_at": datetime.now(timezone.utc).isoformat()}
    start_handoff(state, manual_coating_progress(state, cutting_enabled=config.cutting_workflow_enabled),
                  handoff_id, box["orderId"], box["orderKey"], box["operator"])
    flow["items"][-1]["handoffId"] = handoff_id


def operate(state, flow, config, workspace, action, now):
    kind = action["type"]
    worker_actions = ACTIONS[workspace]
    if workspace == "taping" and kind in {"handoff-confirm", "handoff-close"}:
        require(flow["mode"] == "live" and flow["shift"]["active"], "Açık bantlama vardiyası gerekli.", 409)
        handoff = active_handoff(state, flow)
        require(handoff and handoff["id"] == action.get("id"), "Teslim kaydı değişti.", 409)
        operation = "confirm" if kind == "handoff-confirm" else "close"
        resolve_handoff(state, handoff["id"], operation, action.get("itemId", ""), action.get("measureId", ""))
        reconcile_items(state, flow, now)
        return
    require(kind in worker_actions, "Bu alanda bu işlem yapılamaz.", 403)
    box = flow.get("activeBox")
    by_id = {row["id"]: row for row in flow["orders"]}
    if kind == "start-box":
        order = by_id.get(flow["activeOrder"])
        require(order and not order.get("closedAt"), "Aktif iş emri gerekli.", 409)
        reason = taping_block(state, config, flow["mode"])
        require(not reason, reason, 409)
    if kind == "pack":
        item = next((row for row in flow["items"] if row["id"] == action.get("itemId")), None)
        order = by_id.get(item["orderId"]) if item else None
        require(order and not order.get("closedAt") and item["orderKey"] == order["key"],
                "Bu kutunun iş emri artık açık değil.", 409)
    actor = {"id": workspace, "name": "Mühendis" if workspace == "engineer" else "", "role": workspace,
             "pairedTablet": workspace != "engineer", "stationId": {"taping": "BNT-01", "packing": "PKT-01"}.get(workspace)}
    apply_action(flow, action, actor, now)
    if kind == "start-box":
        flow["activeBox"]["orderKey"] = by_id[flow["activeBox"]["orderId"]]["key"]
    if kind == "finish-box" and action.get("outcome") == "good" and flow["mode"] == "live":
        finish_live_box(state, flow, config, box)
    if flow["mode"] == "live" and not flow["activeBox"]:
        current = state["workOrders"]["activeOrderId"]
        flow["activeOrder"] = current if current in by_id else None
    for order in flow["orders"]:
        details = {key: order[key] for key in ("rank", "closedAt", "closedBy", "parkedAt", "parkReason",
                                               "parkHistory", "productionPlan") if key in order}
        flow["orderDetails"][order["key"]] = details


def active_handoff(state, flow):
    for item in reversed(flow["items"]):
        handoff = state["conveyorHandoffs"].get(item.get("handoffId"))
        if handoff and handoff["status"] in PENDING_STATUSES:
            return {key: handoff[key] for key in ("id", "status", "candidate")}
    return None


def panel_snapshot(state, flow, workspace, now, read_only, config):
    orders = flow["orders"]
    all_items = flow["items"]
    order_keys = {(order["id"], order["key"]) for order in orders}
    items = [item for item in all_items if (item["orderId"], item.get("orderKey")) in order_keys]
    shift = flow["shift"]
    shifts = flow["stationShifts"]
    spent = sum((stop["end"] if stop["end"] is not None else now) - stop["start"] for stop in flow["lineStops"])
    visible = {"mode": flow["mode"]}
    if workspace in {"engineer", "taping", "packing"}:
        visible.update(orders=[{key: value for key, value in order.items() if key != "key"} for order in orders],
                       items=[{key: value for key, value in item.items() if key != "orderKey"} for item in items])
    else:
        visible.update(orders=[], items=[])
    if workspace in {"taping", "engineer"}:
        visible.update(activeOrder=flow["activeOrder"], instruction=flow["instruction"],
                       instructionHistory=flow["instructionHistory"], activities=flow["activities"])
    if workspace == "taping":
        box = flow["activeBox"]
        block = taping_block(state, config, flow["mode"])
        visible.update(activeBox={key: value for key, value in box.items() if key != "orderKey"} if box else None,
                       shift=shift, activity=flow["activity"], tape=flow["tape"],
                       handoff=active_handoff(state, flow) if flow["mode"] == "live" else None,
                       tapingReady=not block, tapingBlockReason=block)
    if workspace in {"engineer", "technician"}:
        visible["alerts"] = [alert for alert in flow["alerts"] if workspace == "engineer" or alert["kind"] == "fault"]
    visible["stations"] = [
        {"id": "BNT-01", "name": "Bantlama", "device": "Tablet 01"},
        {"id": "PKT-01", "name": "Paketleme", "device": "Tablet 02",
         "operator": shifts.get("packing", {}).get("operator") or "Vardiya kapalı"},
    ]
    visible["meta"] = {
        "workspace": workspace, "readOnly": read_only, "serverNow": now, "revision": flow["revision"],
        "stationShift": shifts.get(workspace), "performance": {"stopped": spent},
    }
    if workspace == "engineer":
        visible["meta"]["planning"] = planning_snapshot({**flow, "items": items}, now)
    return visible

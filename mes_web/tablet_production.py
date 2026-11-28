"""ERP-backed box production from cutting through packing."""

from collections import Counter
from datetime import datetime, timezone
from uuid import uuid4

from .cutting_workflow import TAPES_PER_BOX, apply_cutting_action
from .manual_coating import manual_coating_order_key, manual_coating_progress
from .station_workflow import COLORS, confirmed, cutting, packing, require, taping, text


TABLET_ACTIONS = {
    "giyotin": {"cut"},
    "bantlama": {"start", "step", "pause", "resume", "finish"},
    "konveyor": {"match", "exit"},
    "paketleme": {"pack", "park", "resume", "seal"},
}
DOWNSTREAM = {"konveyor", "paketleme"}


def has_packing_route(order):
    return bool(order and TABLET_ACTIONS.keys() <= order.get("stationOrders", {}).keys())


def routed_order(state, station, *, show_closed=False):
    work_orders = state["workOrders"]
    order_id = work_orders["activeOrderId"]
    if not order_id and show_closed and station in DOWNSTREAM:
        order_id = work_orders["lastCompletedOrderId"]
    order = work_orders["ordersById"].get(order_id)
    if station in DOWNSTREAM and not has_packing_route(order):
        return None
    progress = manual_coating_progress(state, cutting_enabled=True, order_id=order_id)
    if progress is None:
        return None
    route = order.get("stationOrders", {})
    return (order, progress, route) if {"giyotin", "bantlama"} <= route.keys() else None


def empty_order_run():
    return {
        "revision": 0,
        "activeBox": None,
        "boxes": [],
        "cutLog": [],
        "used": dict.fromkeys(COLORS, 0),
    }


def tablet_view(order, progress, route, run, station):
    color = order["productColor"]
    goals = dict.fromkeys(COLORS, 0)
    cut = dict.fromkeys(COLORS, 0)
    if color in COLORS:
        goals[color] = progress["target_qty"]
        cut[color] = progress["cutting"]["cut_tapes"]
    box = run["activeBox"]
    station_order = route[station]
    available = max(0, (sum(cut.values()) - sum(run["used"].values())) // TAPES_PER_BOX)
    packed = dict.fromkeys(COLORS, 0)
    for row in run["boxes"]:
        if row["stage"] == "packed":
            packed[row["color"]] += 1
    return {
        "orders": [{"id": order["orderId"], "customer": order["stockName"], "qty": order["quantity"]}],
        "erpOrder": {
            "key": progress["order_key"], "stationOrderId": station_order["station_order_id"],
            "color": color, "open": progress["cutting"]["order_open"] and color in COLORS,
            "revision": run["revision"], "cutTapes": progress["cutting"]["cut_tapes"],
        },
        "goals": goals,
        "cut": cut,
        "used": run["used"],
        "cutLog": run["cutLog"],
        "activeBox": box,
        "boxes": run["boxes"],
        "packed": packed,
        "carton": run.get("carton", {"stage": "open", "reason": ""}),
        "wip": [
            {"name": "Bantlamaya hazır", "occupied": available, "capacity": order["quantity"]},
            {"name": "Konveyöre hazır", "occupied": sum(row["stage"] == "handoff" for row in run["boxes"]),
             "capacity": order["quantity"]},
        ],
    }


def board_for_order(state, station):
    context = routed_order(state, station, show_closed=True)
    if context is None:
        return {}
    order, progress, route = context
    run = state["cuttingWorkflow"]["tabletRuns"].get(progress["order_key"])
    board = tablet_view(order, progress, route, run or empty_order_run(), station)
    board["boxes"] = [{"orderId": order["orderId"], **box} for box in board["boxes"]]
    if station == "konveyor":
        board["lineMeasurements"] = [
            {key: row[key] for key in ("item_id", "measure_id", "color")}
            for row in available_measurements(state, progress["order_key"], board["boxes"])
        ]
    return board


def station_event(order, station, kind, box, shift, recorded_at, **fields):
    return {
        "event_uid": f"{station}:{uuid4().hex}", "recorded_at": recorded_at,
        "production_order_id": order["orderId"], "station_order_id": order["stationOrders"][station]["station_order_id"],
        "station_code": station, "event_type_code": kind, "item_id": box["id"],
        "operator": shift["operator"], "quantity": 1, "unit": order["stationOrders"][station]["unit"], **fields,
    }


def box_measurements(state):
    return (row["lineMatch"] for run in state["cuttingWorkflow"]["tabletRuns"].values()
            for row in run["boxes"] if "lineMatch" in row)


def available_measurements(state, order_key, boxes):
    waiting = [box["taping"]["at"] for box in boxes if box["stage"] == "handoff"]
    if not waiting:
        return []
    claimed = {(row["item_id"], row["measure_id"], row["recorded_at"]) for row in box_measurements(state)}
    return [row for item in state["itemsById"].values() if (row := item.get("tabletMeasurement"))
            and row["order_key"] == order_key and row["at_ms"] >= min(waiting)
            and (row["item_id"], row["measure_id"], row["recorded_at"]) not in claimed]


def verify_exit(order, run, box, measurement):
    if box["stage"] != "transit" or not measurement.get("released_at"):
        return False
    match = box["lineMatch"]
    if any(match[key] != measurement[key] for key in ("item_id", "measure_id", "recorded_at", "color")):
        return False
    stamp = measurement["released_at"]
    box.update(stage="exited", completedAt=int(datetime.fromisoformat(stamp).timestamp() * 1000))
    box["exitEvent"] = station_event(order, "konveyor", "conveyor_exit_verified", box, {"operator": ""}, stamp,
                                     measure_id=match["measure_id"], color_code=match["color"], notes=f'MEGA ITEM_ID={match["item_id"]}')
    run["revision"] += 1
    return True


def observe_tablet_exit(state, order, measurement):
    run = state["cuttingWorkflow"]["tabletRuns"].get(manual_coating_order_key(order))
    if run:
        for box in run["boxes"]:
            if verify_exit(order, run, box, measurement):
                break


def match_conveyor_box(state, order, run, action, fields, shift):
    require(action == "match", "Fiziksel çıkış için eşleşen robot bırakma kaydı gerekli.")
    box = next((row for row in run["boxes"] if row["id"] == fields.get("box")), None)
    require(box is not None and box["outcome"] == "good", "Kutu konveyör teslimine hazır değil.")
    measure_id = text(fields, "measurement", "Hat ölçüm kimliğini", 60)
    item_id = text(fields, "lineItemId", "Hat parça kimliğini", 60)
    if box.get("lineMatch"):
        match = box["lineMatch"]
        require((item_id, measure_id) == (match["item_id"], match["measure_id"]), "Kutu başka bir ölçümle eşleşmiş.")
        return f'{box["id"]} ölçüm eşleşmesi daha önce kaydedildi.', False
    matches = [row for row in available_measurements(state, manual_coating_order_key(order), [box])
               if (row["item_id"], row["measure_id"]) == (item_id, measure_id)]
    require(len(matches) == 1, "Bu kutu için doğrulanabilir hat ölçümü bulunamadı.")
    measurement = matches[0]
    require(measurement["color"] == box["color"], "Ölçülen renk kutunun iş emrine uymuyor.")
    box.update(stage="transit", measurement=measure_id,
               lineMatch={key: measurement[key] for key in ("item_id", "measure_id", "recorded_at", "color")})
    box["matchEvent"] = station_event(order, "konveyor", "conveyor_matched", box, shift, datetime.now(timezone.utc).isoformat(),
                                      measure_id=measure_id, color_code=measurement["color"], notes=f"MEGA ITEM_ID={item_id}")
    verify_exit(order, run, box, measurement)
    return f'{box["id"]} hat ölçümüyle eşleştirildi.', True


def reserve_cut_events(workflow, order_id, order_key, boxes):
    used = Counter()
    for box in boxes:
        used.update(box.get("cutEvents", {}))
    events = []
    for request_id, row in workflow["receipts"].items():
        action = row["action"]
        if action["operation"] == "cut" and (action["order_id"], action["order_key"]) == (order_id, order_key):
            events.append((row["recorded_at"], f"giyotin:manual:{request_id}", action["quantity"]))
    for event_id, row in workflow["protocol4"].get("events", {}).items():
        if row.get("count") and (row.get("orderId"), row.get("orderKey")) == (order_id, order_key):
            events.append((row["recordedAt"], f"giyotin:nano:{event_id}", row["count"]))
    allocated = {}
    remaining = TAPES_PER_BOX
    for _, uid, count in sorted(events):
        take = min(remaining, count - used[uid])
        if take > 0:
            allocated[uid] = take
            remaining -= take
        if not remaining:
            break
    return allocated


def record_tablet_action(state, station, action, fields, shift, finalize_order):
    workflow = state["cuttingWorkflow"]
    if station == "paketleme" and action == "seal" and isinstance(fields.get("orderKey"), str):
        closed = workflow["tabletRuns"].get(fields["orderKey"], {}).get("erpClosure")
        if closed:
            return "Koli kapanışı daha önce kaydedildi.", False
    context = routed_order(state, station)
    if context is None:
        require(not fields.get("orderKey"), "Aktif ERP iş emri değişti. Ekranı yenileyin.")
        return None, False
    order, progress, route = context
    require(fields.get("orderKey") == progress["order_key"], "Aktif ERP iş emri değişti. Ekranı yenileyin.")
    require(shift is not None, "Bu işleme başlamadan önce vardiyayı açın.")
    require(progress["cutting"]["order_open"], "ERP iş emri işleme açık değil.")
    require(order["productColor"] in COLORS, "ERP iş emrinin bant rengi belirli olmalı.")
    if action in {"cut", "start"}:
        require(fields.get("color") == order["productColor"], "Seçilen bant rengi ERP iş emrine uymuyor.")

    run = workflow["tabletRuns"].setdefault(progress["order_key"], empty_order_run())
    view = tablet_view(order, progress, route, run, station)
    working = {**view, "shifts": {station: shift}}
    if station == "giyotin":
        before = len(run["cutLog"])
        message = cutting(working, action, fields)
        if len(run["cutLog"]) == before:
            return message, False
        record = run["cutLog"][0]
        if record["result"] == "good":
            request_id = record["requestId"]
            require(request_id not in state["manualCoatingRecords"], "Kesim kayıt kimliği kullanımda.")
            try:
                duplicate = apply_cutting_action(state, progress, request_id, {
                    "operation": "cut", "order_id": order["orderId"], "order_key": progress["order_key"],
                    "operator": shift["operator"], "quantity": record["count"],
                })
            except ValueError as error:
                require(False, str(error))
            require(not duplicate, "Kesim kayıt kimliği kullanımda.")
    elif station == "bantlama":
        message = taping(working, action, fields)
        run["activeBox"] = working["activeBox"]
        if action == "start":
            run["activeBox"]["cutEvents"] = reserve_cut_events(workflow, order["orderId"], progress["order_key"], run["boxes"])
        if action == "finish":
            completed = run["boxes"][-1]
            completed.update(orderId=order["orderId"], cutEvents=view["activeBox"].get("cutEvents", {}))
        if action == "finish" and run["boxes"][-1]["outcome"] == "good":
            completed = run["boxes"][-1]
            completed["productionEvent"] = {
                "event_uid": f'bantlama:manual:{progress["order_key"]}:{completed["id"]}',
                "recorded_at": datetime.fromtimestamp(completed["taping"]["at"] / 1000, timezone.utc).isoformat(),
                "production_order_id": order["orderId"], "station_order_id": route[station]["station_order_id"],
                "station_code": station, "event_type_code": "taping_completed", "item_id": completed["id"],
                "operator": shift["operator"], "quantity": 1, "unit": route[station]["unit"],
                "notes": "; ".join(f"{uid} ({count})" for uid, count in completed["cutEvents"].items()),
            }
    elif station == "konveyor":
        message, changed = match_conveyor_box(state, order, run, action, fields, shift)
        if not changed:
            return message, False
    else:
        if action == "seal":
            confirmed(fields, "confirmed", "Paket kapanışı")
        message = packing(working, action, fields)
        run["carton"] = working["carton"]
        if action == "seal":
            packed = [box for box in run["boxes"] if box["stage"] == "packed"]
            stamp = datetime.now(timezone.utc).isoformat()
            for box in packed:
                box["packingEvent"] = station_event(order, station, "packing_closed", box, shift, stamp,
                                                   measure_id=box["measurement"], color_code=box["color"])
            finalize_order(state, order, run, packed, stamp)
    run["revision"] += 1
    return message, True

from __future__ import annotations
import copy
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .command_policy import is_local_only_command
from .config import AppConfig
from .masterdata import load_kiosk_masterdata
from .oee_state import WorkOrderTransitionReasonRequired, build_work_order_snapshot
from .parsers import normalize_color
from .runtime import RuntimeService, SnapshotHub
from .store import DashboardStore, utc_now_text
from .windows_asyncio import install_windows_connection_reset_filter


config = AppConfig.from_env()
store = DashboardStore(config)
hub = SnapshotHub(store, coalesce_ms=config.ws_coalesce_ms)
runtime_service = RuntimeService(config, store, hub)
oee_state_manager = runtime_service.oee_manager


def _is_benign_socket_disconnect_error(exc: BaseException) -> bool:
    return isinstance(exc, OSError) and getattr(exc, "winerror", None) in {121, 10054}


def _catalog_operator(catalog: dict[str, Any], token: Any) -> dict[str, str] | None:
    normalized = str(token or "").strip()
    if not normalized:
        return None
    for row in catalog.get("operators", []):
        if not isinstance(row, dict):
            continue
        if normalized in {
            str(row.get("operator_id") or "").strip(),
            str(row.get("operator_code") or "").strip(),
        }:
            return {
                "operator_id": str(row.get("operator_id") or "").strip(),
                "operator_code": str(row.get("operator_code") or "").strip(),
                "operator_name": str(row.get("operator_name") or "").strip(),
            }
    return None


def _catalog_station(catalog: dict[str, Any], station_id: Any) -> dict[str, str] | None:
    normalized = str(station_id or "").strip()
    if not normalized:
        return None
    for row in catalog.get("stations", []):
        if not isinstance(row, dict):
            continue
        if normalized in {
            str(row.get("station_id") or "").strip(),
            str(row.get("station_code") or "").strip(),
        }:
            return {
                "station_id": str(row.get("station_id") or "").strip(),
                "station_code": str(row.get("station_code") or "").strip(),
                "station_name_tr": str(row.get("station_name_tr") or "").strip(),
                "line_id": str(row.get("line_id") or "").strip(),
            }
    return None


def _find_kiosk_item_state(state: dict[str, Any], item_id: str, completed_at: str) -> dict[str, Any] | None:
    items = state.get("itemsById") if isinstance(state.get("itemsById"), dict) else {}
    exact_match: dict[str, Any] | None = None
    fallback: tuple[str, dict[str, Any]] | None = None
    for item in items.values():
        if not isinstance(item, dict):
            continue
        if str(item.get("item_id") or "").strip() != item_id:
            continue
        item_completed_at = str(item.get("completed_at") or "").strip()
        if not item_completed_at:
            continue
        if item_completed_at == completed_at:
            exact_match = item
            break
        rank = item_completed_at
        if fallback is None or rank > fallback[0]:
            fallback = (rank, item)
    return exact_match or (fallback[1] if fallback is not None else None)


def _display_color_code(*values: Any) -> str:
    for candidate in values:
        text = str(candidate or "").strip()
        if not text:
            continue
        normalized = normalize_color(text)
        if normalized in {"red", "yellow", "blue"}:
            return normalized
        upper = text.upper()
        if "KIRMIZI" in upper or "RED" in upper:
            return "red"
        if "MAVI" in upper or "BLUE" in upper:
            return "blue"
        if "SARI" in upper or "YELLOW" in upper:
            return "yellow"
    return ""


def _display_color_label(color_code: Any) -> str:
    return {
        "red": "Kirmizi",
        "blue": "Mavi",
        "yellow": "Sari",
    }.get(str(color_code or "").strip().lower(), "Bilinmeyen")


def _project_kiosk_requirements(order: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, int], str]:
    raw_requirements = order.get("requirements") if isinstance(order.get("requirements"), list) else []
    projected: list[dict[str, Any]] = []
    content_counts = {"red": 0, "blue": 0, "yellow": 0}
    for index, row in enumerate(raw_requirements, start=1):
        if not isinstance(row, dict):
            continue
        color_code = _display_color_code(
            row.get("color"),
            row.get("matchKey"),
            row.get("stockCode"),
            row.get("stockName"),
        )
        qty = max(0, round(float(row.get("quantity") or row.get("qty") or 0)))
        projected.append(
            {
                "line_id": str(row.get("lineId") or row.get("line_id") or index),
                "stock_code": str(row.get("stockCode") or row.get("stock_code") or ""),
                "stock_name": str(row.get("stockName") or row.get("stock_name") or ""),
                "color": color_code,
                "color_label": _display_color_label(color_code),
                "qty": qty,
            }
        )
        if color_code in content_counts:
            content_counts[color_code] += qty
    if not projected:
        color_code = _display_color_code(
            order.get("productColor"),
            order.get("matchKey"),
            order.get("stockCode"),
            order.get("stockName"),
        )
        qty = max(0, round(float(order.get("quantity") or 0)))
        projected.append(
            {
                "line_id": "default",
                "stock_code": str(order.get("stockCode") or ""),
                "stock_name": str(order.get("stockName") or ""),
                "color": color_code,
                "color_label": _display_color_label(color_code),
                "qty": qty,
            }
        )
        if color_code in content_counts:
            content_counts[color_code] += qty
    content_summary = " | ".join(
        f"{_display_color_label(color_code)} {content_counts[color_code]}"
        for color_code in ("red", "blue", "yellow")
    )
    return projected, content_counts, content_summary


def _queued_order_ids(raw_orders: dict[str, Any], sequence: list[Any]) -> list[str]:
    queued: list[str] = []
    seen: set[str] = set()
    for raw_order_id in sequence:
        order_id = str(raw_order_id or "").strip()
        order = raw_orders.get(order_id)
        if not order_id or order_id in seen or not isinstance(order, dict):
            continue
        if str(order.get("status") or "").strip() != "queued":
            continue
        queued.append(order_id)
        seen.add(order_id)
    for raw_order_id, order in raw_orders.items():
        order_id = str(raw_order_id or "").strip()
        if not order_id or order_id in seen or not isinstance(order, dict):
            continue
        if str(order.get("status") or "").strip() != "queued":
            continue
        queued.append(order_id)
        seen.add(order_id)
    return queued


def _project_kiosk_work_order(order_id: str, order: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    snapshot = build_work_order_snapshot(state, order)
    quantity = int(snapshot.get("targetQty") or 0)
    completed_qty = int(snapshot.get("fulfilledQty") or 0)
    remaining_qty = int(snapshot.get("remainingQty") or 0)
    requirements, content_counts, content_summary = _project_kiosk_requirements(order)
    return {
        "order_id": str(order_id or ""),
        "status": str(order.get("status") or "queued"),
        "acceptance_pending": str(order.get("status") or "") == "pending_approval",
        "stock_code": str(order.get("stockCode") or ""),
        "stock_name": str(order.get("stockName") or ""),
        "product_color": str(order.get("productColor") or ""),
        "requirements": requirements,
        "content_counts": content_counts,
        "content_summary": content_summary,
        "qty": quantity,
        "completed_qty": completed_qty,
        "remaining_qty": remaining_qty,
        "progress_pct": round((completed_qty / quantity) * 100.0, 1) if quantity > 0 else 0.0,
        "started_at": order.get("startedAt"),
        "completed_at": order.get("completedAt"),
        "started_by": str(order.get("startedBy") or ""),
        "started_by_name": str(order.get("startedByName") or ""),
        "transition_reason": str(order.get("transitionReason") or ""),
    }


def _checklist_ready(session: dict[str, Any] | None) -> bool:
    if not isinstance(session, dict):
        return False
    for step in session.get("steps") if isinstance(session.get("steps"), list) else []:
        if not isinstance(step, dict):
            continue
        if bool(step.get("required", True)) and not bool(step.get("completed")):
            return False
    return True


def _find_open_help_request(state: dict[str, Any], device_id: str, bound_station_id: str) -> dict[str, Any] | None:
    help_request = state.get("helpRequest") if isinstance(state.get("helpRequest"), dict) else {}
    requests_by_key = help_request.get("requestsByKey") if isinstance(help_request.get("requestsByKey"), dict) else {}
    request = requests_by_key.get(f"{device_id}:{bound_station_id}")
    if isinstance(request, dict) and str(request.get("status") or "") in {"open", "acknowledged"}:
        return request
    for row in requests_by_key.values():
        if not isinstance(row, dict):
            continue
        if str(row.get("deviceId") or "").strip() != device_id:
            continue
        if str(row.get("status") or "").strip() not in {"open", "acknowledged"}:
            continue
        return row
    return None


def _kiosk_big_action(
    *,
    operational_state: str,
    active_order: dict[str, Any] | None,
    queue_orders: list[dict[str, Any]],
    opening_session: dict[str, Any] | None,
    closing_session: dict[str, Any] | None,
) -> dict[str, Any]:
    if operational_state == "opening_checklist":
        return {
            "action": "maintenance_complete",
            "label": "Acilis Bakimini Tamamla",
            "enabled": _checklist_ready(opening_session),
            "phase": "opening",
        }
    if operational_state == "manual_fault_active":
        return {
            "action": "wait",
            "label": "Ariza Grubundan Kapat",
            "enabled": False,
            "phase": "",
        }
    if operational_state == "closing_checklist":
        return {
            "action": "maintenance_complete",
            "label": "Kapanis Bakimini Tamamla ve Vardiyayi Kapat",
            "enabled": _checklist_ready(closing_session),
            "phase": "closing",
        }
    if operational_state == "idle_ready":
        return {
            "action": "shift_start",
            "label": "Vardiya Baslat",
            "enabled": True,
            "phase": "opening",
        }
    if isinstance(active_order, dict) and str(active_order.get("status") or "") == "pending_approval":
        return {
            "action": "work_order_accept",
            "label": "Onayla ve Kapat",
            "enabled": True,
            "phase": "",
        }
    if isinstance(active_order, dict) and str(active_order.get("status") or "") == "active":
        return {
            "action": "wait",
            "label": "Aktif Is Emri Calisiyor",
            "enabled": False,
            "phase": "",
        }
    if queue_orders:
        return {
            "action": "work_order_start_next",
            "label": "Siradaki Isi Baslat",
            "enabled": True,
            "phase": "",
        }
    return {
        "action": "wait",
        "label": "Is Emri Bekleniyor",
        "enabled": False,
        "phase": "",
    }


def _build_kiosk_snapshot(module_id: str, device_id: str) -> dict[str, Any]:
    dashboard = store.get_dashboard_snapshot(module_id)
    state = oee_state_manager.read_state()
    catalog = load_kiosk_masterdata(config)
    device_registry = state.get("deviceRegistry") if isinstance(state.get("deviceRegistry"), dict) else {}
    device_sessions = state.get("deviceSessions") if isinstance(state.get("deviceSessions"), dict) else {}
    device_entry = device_registry.get(device_id) if isinstance(device_registry.get(device_id), dict) else {}
    session_entry = device_sessions.get(device_id) if isinstance(device_sessions.get(device_id), dict) else {}
    bound_station_id = (
        str(device_entry.get("boundStationId") or "").strip()
        or str(session_entry.get("boundStationId") or "").strip()
        or str(((catalog.get("defaults") or {}) if isinstance(catalog.get("defaults"), dict) else {}).get("bound_station_id") or "").strip()
    )
    current_operator = _catalog_operator(
        catalog,
        session_entry.get("operatorId") or device_entry.get("lastOperatorId") or "",
    )
    active_help_request = _find_open_help_request(state, device_id, bound_station_id)
    work_orders_payload = state.get("workOrders") if isinstance(state.get("workOrders"), dict) else {}
    raw_orders = work_orders_payload.get("ordersById") if isinstance(work_orders_payload.get("ordersById"), dict) else {}
    sequence = work_orders_payload.get("orderSequence") if isinstance(work_orders_payload.get("orderSequence"), list) else []
    queued_order_ids = _queued_order_ids(raw_orders, sequence)
    ordered_orders: list[dict[str, Any]] = []
    seen_order_ids: set[str] = set()
    for raw_order_id in sequence:
        order_id = str(raw_order_id or "").strip()
        order = raw_orders.get(order_id)
        if not order_id or not isinstance(order, dict):
            continue
        ordered_orders.append(_project_kiosk_work_order(order_id, order, state))
        seen_order_ids.add(order_id)
    for order_id, order in raw_orders.items():
        normalized_id = str(order_id or "").strip()
        if not normalized_id or normalized_id in seen_order_ids or not isinstance(order, dict):
            continue
        ordered_orders.append(_project_kiosk_work_order(normalized_id, order, state))
    active_order = next(
        (
            row
            for row in ordered_orders
            if str(row.get("status") or "") in {"active", "pending_approval"}
        ),
        None,
    )
    queue_orders = [row for row in ordered_orders if str(row.get("status") or "") == "queued"]
    top_queue_order_id = queued_order_ids[0] if queued_order_ids else ""
    for index, row in enumerate(queue_orders, start=1):
        row["queue_rank"] = index
        row["is_top_queue"] = str(row.get("order_id") or "") == top_queue_order_id
    opening_session = ((state.get("maintenance") or {}) if isinstance(state.get("maintenance"), dict) else {}).get("openingSession")
    closing_session = ((state.get("maintenance") or {}) if isinstance(state.get("maintenance"), dict) else {}).get("closingSession")
    recent_items: list[dict[str, Any]] = []
    for row in (dashboard.get("oee") or {}).get("recent_items", [])[:5]:
        if not isinstance(row, dict):
            continue
        item_id = str(row.get("item_id") or "").strip()
        completed_at = str(row.get("completed_at") or "").strip()
        state_item = _find_kiosk_item_state(state, item_id, completed_at)
        work_order_id = str((state_item or {}).get("work_order_id") or "").strip()
        work_order_status = ""
        if work_order_id:
            work_order_status = str(((raw_orders.get(work_order_id) or {}) if isinstance(raw_orders.get(work_order_id), dict) else {}).get("status") or "").strip()
        can_override = bool(completed_at) and (not work_order_id or work_order_status in {"active", "pending_approval"})
        projected = copy.deepcopy(row)
        projected["work_order_id"] = work_order_id
        projected["work_order_status"] = work_order_status
        projected["can_override"] = can_override
        projected["override_reason_text"] = str((state_item or {}).get("override_reason_text") or "")
        projected["display_color"] = _display_color_code(
            row.get("final_color"),
            row.get("color"),
            row.get("sensor_color"),
            (state_item or {}).get("final_color"),
            (state_item or {}).get("color"),
            (state_item or {}).get("sensor_color"),
        )
        projected["color_label"] = _display_color_label(projected["display_color"])
        recent_items.append(projected)
    operational_state = str(state.get("operationalState") or "idle_ready")
    permissions = store.command_permissions()
    return {
        "device": {
            "device_id": device_id,
            "device_name": str(device_entry.get("deviceName") or device_id),
            "device_role": str(device_entry.get("deviceRole") or "operator_kiosk"),
            "bound_station_id": bound_station_id,
            "last_operator_id": str(device_entry.get("lastOperatorId") or ""),
            "last_seen_at": device_entry.get("lastSeenAt"),
        },
        "operator": current_operator,
        "operators": copy.deepcopy(catalog.get("operators") or []),
        "fault_options": [
            {
                **copy.deepcopy(row),
                "fault_reason_tr": (
                    "Robot Kol S\u0131k\u0131\u015fmas\u0131"
                    if str((row or {}).get("fault_type_code") or "").strip() == "robot_arm_jam"
                    else str((row or {}).get("fault_reason_tr") or "")
                ),
            }
            for row in (catalog.get("fault_options") or [])
            if isinstance(row, dict)
        ],
        "stations": copy.deepcopy(catalog.get("stations") or []),
        "line_status": {
            "header": copy.deepcopy(((dashboard.get("oee") or {}) if isinstance(dashboard.get("oee"), dict) else {}).get("header") or {}),
            "kpis": copy.deepcopy(((dashboard.get("oee") or {}) if isinstance(dashboard.get("oee"), dict) else {}).get("kpis") or {}),
            "production": copy.deepcopy(((dashboard.get("oee") or {}) if isinstance(dashboard.get("oee"), dict) else {}).get("production") or {}),
        },
        "work_orders": {
            "active_order": copy.deepcopy(active_order),
            "ordered": copy.deepcopy(ordered_orders),
            "queue": copy.deepcopy(queue_orders),
        },
        "recent_items": recent_items,
        "quality_options": ["GOOD", "REWORK", "SCRAP"],
        "operational_state": operational_state,
        "active_fault": copy.deepcopy(state.get("activeFault")),
        "help_request": copy.deepcopy(active_help_request),
        "system_start": {
            "enabled": bool(permissions.get("publish_enabled")) and "start" in set(permissions.get("allowed_presets") or []) and operational_state in {"idle_ready", "shift_active_running"},
            "label": "Sistem Start",
        },
        "maintenance": {
            "opening_session": copy.deepcopy(opening_session),
            "closing_session": copy.deepcopy(closing_session),
            "opening_steps": copy.deepcopy((((catalog.get("maintenance") or {}) if isinstance(catalog.get("maintenance"), dict) else {}).get("opening_steps")) or []),
            "closing_steps": copy.deepcopy((((catalog.get("maintenance") or {}) if isinstance(catalog.get("maintenance"), dict) else {}).get("closing_steps")) or []),
        },
        "big_action": _kiosk_big_action(
            operational_state=operational_state,
            active_order=active_order,
            queue_orders=queue_orders,
            opening_session=opening_session if isinstance(opening_session, dict) else None,
            closing_session=closing_session if isinstance(closing_session, dict) else None,
        ),
        "timestamps": {
            "snapshot_at": utc_now_text(),
            "last_updated_at": state.get("lastUpdatedAt"),
        },
    }


def create_app() -> FastAPI:
    app = FastAPI(title="MES Web", version="0.1.0")
    static_dir = Path(config.static_dir)
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    def sync_work_order_runtime(state: dict[str, Any] | None = None) -> None:
        runtime_state = state if isinstance(state, dict) else oee_state_manager.read_state()
        runtime_service.excel_sink.record_work_order_state(runtime_state, utc_now_text())

    def _ensure_module(module_id: str) -> None:
        if module_id != config.module_id:
            raise HTTPException(status_code=404, detail="MODULE_NOT_FOUND")

    def _device_defaults(device_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        state = oee_state_manager.read_state()
        registry = state.get("deviceRegistry") if isinstance(state.get("deviceRegistry"), dict) else {}
        sessions = state.get("deviceSessions") if isinstance(state.get("deviceSessions"), dict) else {}
        catalog = load_kiosk_masterdata(config)
        return (
            registry.get(device_id) if isinstance(registry.get(device_id), dict) else {},
            sessions.get(device_id) if isinstance(sessions.get(device_id), dict) else {},
            catalog,
        )

    def _resolve_kiosk_actor(payload: dict[str, Any]) -> dict[str, str]:
        device_id = str(payload.get("device_id") or payload.get("deviceId") or "").strip()
        if not device_id:
            raise HTTPException(status_code=400, detail="DEVICE_ID_REQUIRED")
        device_entry, session_entry, catalog = _device_defaults(device_id)
        station_token = (
            str(payload.get("bound_station_id") or payload.get("boundStationId") or "").strip()
            or str(device_entry.get("boundStationId") or "").strip()
            or str(session_entry.get("boundStationId") or "").strip()
            or str(((catalog.get("defaults") or {}) if isinstance(catalog.get("defaults"), dict) else {}).get("bound_station_id") or "").strip()
        )
        station = _catalog_station(catalog, station_token)
        if station_token and station is None:
            raise HTTPException(status_code=400, detail="INVALID_BOUND_STATION")
        operator_token = (
            str(payload.get("operator_id") or payload.get("operatorId") or "").strip()
            or str(payload.get("operator_code") or payload.get("operatorCode") or "").strip()
            or str(session_entry.get("operatorId") or "").strip()
            or str(device_entry.get("lastOperatorId") or "").strip()
        )
        operator = _catalog_operator(catalog, operator_token) if operator_token else None
        if operator_token and operator is None:
            raise HTTPException(status_code=400, detail="INVALID_OPERATOR")
        return {
            "device_id": device_id,
            "device_name": str(payload.get("device_name") or payload.get("deviceName") or device_entry.get("deviceName") or device_id).strip() or device_id,
            "device_role": str(payload.get("device_role") or payload.get("deviceRole") or device_entry.get("deviceRole") or "operator_kiosk").strip() or "operator_kiosk",
            "bound_station_id": str((station or {}).get("station_id") or station_token or ""),
            "operator_id": str((operator or {}).get("operator_id") or ""),
            "operator_code": str((operator or {}).get("operator_code") or ""),
            "operator_name": str((operator or {}).get("operator_name") or ""),
        }

    def _record_kiosk_event(event_type: str, payload: dict[str, Any], *, received_at: str) -> None:
        runtime_service.excel_sink.record_kiosk_event(event_type, payload, received_at)

    def _refresh_after_kiosk_write(module_id: str, state: dict[str, Any] | None) -> None:
        store.refresh_oee_runtime_state(module_id, force=True)
        sync_work_order_runtime(state)

    @app.on_event("startup")
    async def on_startup() -> None:
        install_windows_connection_reset_filter()
        await runtime_service.start()

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        await runtime_service.stop()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "time": utc_now_text()}

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(
            static_dir / "index.html",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    @app.get("/kiosk/{device_id}")
    async def kiosk_index(device_id: str) -> FileResponse:
        if not str(device_id or "").strip():
            raise HTTPException(status_code=400, detail="DEVICE_ID_REQUIRED")
        return FileResponse(
            static_dir / "kiosk.html",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    @app.get("/api/modules")
    async def list_modules() -> list[dict[str, Any]]:
        return store.modules_summary()

    @app.get("/api/modules/{module_id}/dashboard")
    async def get_dashboard(module_id: str) -> dict[str, Any]:
        try:
            return store.get_dashboard_snapshot(module_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="MODULE_NOT_FOUND") from exc

    @app.get("/api/modules/{module_id}/kiosk/bootstrap")
    async def get_kiosk_bootstrap(module_id: str, device_id: str) -> dict[str, Any]:
        _ensure_module(module_id)
        if not str(device_id or "").strip():
            raise HTTPException(status_code=400, detail="DEVICE_ID_REQUIRED")
        store.refresh_oee_runtime_state(module_id, force=True)
        return _build_kiosk_snapshot(module_id, str(device_id).strip())

    @app.post("/api/modules/{module_id}/kiosk/register")
    async def register_kiosk_device(module_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        _ensure_module(module_id)
        actor = _resolve_kiosk_actor(payload)
        try:
            result = oee_state_manager.register_kiosk_device(
                device_id=actor["device_id"],
                device_name=actor["device_name"],
                device_role=actor["device_role"],
                bound_station_id=actor["bound_station_id"],
                operator_id=actor["operator_id"],
                operator_code=actor["operator_code"],
                operator_name=actor["operator_name"],
            )
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc
        _refresh_after_kiosk_write(module_id, result.get("state") if isinstance(result.get("state"), dict) else None)
        store.append_system_log(
            module_id,
            f"SYSTEM|KIOSK|REGISTER|DEVICE={actor['device_id']}|OPERATOR={actor['operator_code'] or actor['operator_id']}",
            topic="local/kiosk",
        )
        return {
            "status": "accepted",
            "device": result.get("device") if isinstance(result.get("device"), dict) else {},
            "session": result.get("session") if isinstance(result.get("session"), dict) else {},
        }

    @app.post("/api/modules/{module_id}/kiosk/shift/start")
    async def kiosk_shift_start(module_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        _ensure_module(module_id)
        actor = _resolve_kiosk_actor(payload)
        catalog = load_kiosk_masterdata(config)
        try:
            result = oee_state_manager.begin_maintenance_session(
                "opening",
                steps=copy.deepcopy((((catalog.get("maintenance") or {}) if isinstance(catalog.get("maintenance"), dict) else {}).get("opening_steps")) or []),
                device_id=actor["device_id"],
                device_name=actor["device_name"],
                device_role=actor["device_role"],
                bound_station_id=actor["bound_station_id"],
                operator_id=actor["operator_id"],
                operator_code=actor["operator_code"],
                operator_name=actor["operator_name"],
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc
        stamp = utc_now_text()
        _refresh_after_kiosk_write(module_id, result.get("state") if isinstance(result.get("state"), dict) else None)
        session = result.get("session") if isinstance(result.get("session"), dict) else {}
        _record_kiosk_event(
            "maintenance_opening_started",
            {
                **actor,
                "session_id": str(session.get("sessionId") or ""),
                "phase": "opening",
                "status": "active",
            },
            received_at=stamp,
        )
        store.append_system_log(
            module_id,
            f"SYSTEM|KIOSK|SHIFT_START_REQUEST|DEVICE={actor['device_id']}|OPERATOR={actor['operator_code'] or actor['operator_id']}",
            topic="local/kiosk",
            received_at=stamp,
        )
        return {
            "status": "accepted",
            "summary": str(result.get("summary") or ""),
            "session": session,
        }

    @app.post("/api/modules/{module_id}/kiosk/shift/stop")
    async def kiosk_shift_stop(module_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        _ensure_module(module_id)
        actor = _resolve_kiosk_actor(payload)
        catalog = load_kiosk_masterdata(config)
        try:
            result = oee_state_manager.begin_maintenance_session(
                "closing",
                steps=copy.deepcopy((((catalog.get("maintenance") or {}) if isinstance(catalog.get("maintenance"), dict) else {}).get("closing_steps")) or []),
                device_id=actor["device_id"],
                device_name=actor["device_name"],
                device_role=actor["device_role"],
                bound_station_id=actor["bound_station_id"],
                operator_id=actor["operator_id"],
                operator_code=actor["operator_code"],
                operator_name=actor["operator_name"],
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc
        stamp = utc_now_text()
        _refresh_after_kiosk_write(module_id, result.get("state") if isinstance(result.get("state"), dict) else None)
        session = result.get("session") if isinstance(result.get("session"), dict) else {}
        _record_kiosk_event(
            "maintenance_closing_started",
            {
                **actor,
                "session_id": str(session.get("sessionId") or ""),
                "phase": "closing",
                "status": "active",
            },
            received_at=stamp,
        )
        store.append_system_log(
            module_id,
            f"SYSTEM|KIOSK|SHIFT_STOP_REQUEST|DEVICE={actor['device_id']}|OPERATOR={actor['operator_code'] or actor['operator_id']}",
            topic="local/kiosk",
            received_at=stamp,
        )
        return {
            "status": "accepted",
            "summary": str(result.get("summary") or ""),
            "session": session,
        }

    @app.post("/api/modules/{module_id}/kiosk/maintenance/complete")
    async def kiosk_complete_maintenance(module_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        _ensure_module(module_id)
        actor = _resolve_kiosk_actor(payload)
        phase = str(payload.get("phase") or payload.get("maintenance_phase") or "").strip().lower()
        if phase not in {"opening", "closing"}:
            raise HTTPException(status_code=400, detail="INVALID_MAINTENANCE_PHASE")
        try:
            result = oee_state_manager.complete_maintenance_session(
                phase,
                completed_steps=payload.get("completed_steps") or payload.get("completedSteps") or [],
                note=str(payload.get("note") or "").strip(),
                device_id=actor["device_id"],
                device_name=actor["device_name"],
                device_role=actor["device_role"],
                bound_station_id=actor["bound_station_id"],
                operator_id=actor["operator_id"],
                operator_code=actor["operator_code"],
                operator_name=actor["operator_name"],
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc
        stamp = utc_now_text()
        updated_state = result.get("state") if isinstance(result.get("state"), dict) else None
        _refresh_after_kiosk_write(module_id, updated_state)
        session = result.get("session") if isinstance(result.get("session"), dict) else {}
        for step in session.get("steps") if isinstance(session.get("steps"), list) else []:
            if not isinstance(step, dict) or not bool(step.get("completed")):
                continue
            _record_kiosk_event(
                "maintenance_step_completed",
                {
                    **actor,
                    "session_id": str(session.get("sessionId") or ""),
                    "phase": phase,
                    "step_code": str(step.get("stepCode") or ""),
                    "step_label": str(step.get("stepLabel") or ""),
                    "note": str(session.get("note") or ""),
                },
                received_at=str(step.get("completedAt") or stamp),
            )
        _record_kiosk_event(
            "maintenance_completed",
            {
                **actor,
                "session_id": str(session.get("sessionId") or ""),
                "phase": phase,
                "status": "completed",
                "note": str(session.get("note") or ""),
            },
            received_at=str(session.get("endedAt") or stamp),
        )
        system_line = str(result.get("system_line") or "").strip()
        if system_line:
            store.append_system_log(module_id, system_line, topic="local/oee", received_at=stamp)
            runtime_service.excel_sink.record_system_oee_log(system_line, stamp)
        return {
            "status": "accepted",
            "summary": str(result.get("summary") or ""),
            "session": session,
        }

    @app.post("/api/modules/{module_id}/kiosk/fault/start")
    async def kiosk_start_fault(module_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        _ensure_module(module_id)
        actor = _resolve_kiosk_actor(payload)
        fault_code = str(payload.get("reason_code") or payload.get("reasonCode") or "").strip()
        fault_text = str(payload.get("reason_text") or payload.get("reasonText") or "").strip()
        catalog = load_kiosk_masterdata(config)
        if fault_code and not fault_text:
            for option in catalog.get("fault_options", []):
                if not isinstance(option, dict):
                    continue
                if fault_code in {str(option.get("fault_type_code") or "").strip(), str(option.get("fault_type_id") or "").strip()}:
                    fault_text = str(option.get("fault_reason_tr") or fault_code)
                    break
        if not fault_code and not fault_text:
            raise HTTPException(status_code=400, detail="FAULT_REASON_REQUIRED")
        try:
            runtime_service.mqtt_client.publish_command("stop")
        except RuntimeError as exc:
            detail = str(exc)
            status_code = 503 if detail.startswith("MQTT_") else 500
            raise HTTPException(status_code=status_code, detail=detail) from exc
        try:
            result = oee_state_manager.start_manual_fault(
                device_id=actor["device_id"],
                reason_code=fault_code,
                reason_text=fault_text,
                device_name=actor["device_name"],
                device_role=actor["device_role"],
                bound_station_id=actor["bound_station_id"],
                operator_id=actor["operator_id"],
                operator_code=actor["operator_code"],
                operator_name=actor["operator_name"],
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc
        stamp = utc_now_text()
        updated_state = result.get("state") if isinstance(result.get("state"), dict) else None
        _refresh_after_kiosk_write(module_id, updated_state)
        fault = result.get("fault") if isinstance(result.get("fault"), dict) else {}
        _record_kiosk_event(
            "kiosk_fault_started",
            {
                **actor,
                "fault_code": fault_code,
                "reason": fault_text,
                "status": "open",
            },
            received_at=str(fault.get("startedAt") or stamp),
        )
        store.append_system_log(
            module_id,
            f"SYSTEM|KIOSK|FAULT_START|DEVICE={actor['device_id']}|REASON={fault_text or fault_code}",
            topic="local/kiosk",
            received_at=stamp,
        )
        return {
            "status": "accepted",
            "summary": str(result.get("summary") or ""),
            "fault": fault,
        }

    @app.post("/api/modules/{module_id}/kiosk/fault/clear")
    async def kiosk_clear_fault(module_id: str) -> dict[str, Any]:
        _ensure_module(module_id)
        state_before = oee_state_manager.read_state()
        active_fault = state_before.get("activeFault") if isinstance(state_before.get("activeFault"), dict) else {}
        try:
            result = oee_state_manager.clear_manual_fault()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc
        stamp = utc_now_text()
        _refresh_after_kiosk_write(module_id, result.get("state") if isinstance(result.get("state"), dict) else None)
        _record_kiosk_event(
            "kiosk_fault_cleared",
            {
                "device_id": str(active_fault.get("deviceId") or ""),
                "bound_station_id": str(active_fault.get("boundStationId") or ""),
                "operator_id": str(active_fault.get("operatorId") or ""),
                "fault_code": str(active_fault.get("reasonCode") or ""),
                "reason": str(active_fault.get("reason") or ""),
                "status": "resolved",
            },
            received_at=stamp,
        )
        store.append_system_log(module_id, "SYSTEM|KIOSK|FAULT_CLEAR", topic="local/kiosk", received_at=stamp)
        return {
            "status": "accepted",
            "summary": str(result.get("summary") or ""),
        }

    @app.post("/api/modules/{module_id}/kiosk/help/request")
    async def kiosk_request_help(module_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        _ensure_module(module_id)
        actor = _resolve_kiosk_actor(payload)
        try:
            result = oee_state_manager.request_help(
                device_id=actor["device_id"],
                device_name=actor["device_name"],
                bound_station_id=actor["bound_station_id"],
                operator_id=actor["operator_id"],
                operator_code=actor["operator_code"],
                operator_name=actor["operator_name"],
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc
        stamp = utc_now_text()
        _refresh_after_kiosk_write(module_id, result.get("state") if isinstance(result.get("state"), dict) else None)
        request_row = result.get("request") if isinstance(result.get("request"), dict) else {}
        _record_kiosk_event(
            "help_requested",
            {
                **actor,
                "status": str(request_row.get("status") or "open"),
                "repeat_count": int(request_row.get("repeatCount") or 1),
            },
            received_at=str(request_row.get("lastRequestedAt") or stamp),
        )
        store.append_system_log(
            module_id,
            f"SYSTEM|KIOSK|HELP_REQUEST|DEVICE={actor['device_id']}|REPEAT={int(request_row.get('repeatCount') or 1)}",
            topic="local/kiosk",
            received_at=stamp,
        )
        return {
            "status": "accepted",
            "summary": str(result.get("summary") or ""),
            "request": request_row,
        }

    @app.post("/api/modules/{module_id}/kiosk/system/start")
    async def kiosk_system_start(module_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        _ensure_module(module_id)
        actor = _resolve_kiosk_actor(payload)
        permissions = store.command_permissions()
        if "start" not in set(permissions.get("allowed_presets") or []):
            raise HTTPException(status_code=400, detail="UNKNOWN_PRESET_COMMAND")
        if not bool(permissions.get("publish_enabled")):
            raise HTTPException(status_code=409, detail="COMMAND_PUBLISH_DISABLED")
        try:
            runtime_service.mqtt_client.publish_command("start")
        except RuntimeError as exc:
            detail = str(exc)
            status_code = 503 if detail.startswith("MQTT_") else 500
            raise HTTPException(status_code=status_code, detail=detail) from exc
        stamp = utc_now_text()
        store.append_system_log(
            module_id,
            f"SYSTEM|KIOSK|SYSTEM_START|DEVICE={actor['device_id']}|OPERATOR={actor['operator_code'] or actor['operator_id']}",
            topic="local/kiosk",
            received_at=stamp,
        )
        return {
            "status": "accepted",
            "summary": "Sistem start komutu gonderildi.",
        }

    @app.post("/api/modules/{module_id}/kiosk/work-orders/start")
    async def kiosk_start_work_order(module_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        _ensure_module(module_id)
        actor = _resolve_kiosk_actor(payload)
        current_state = oee_state_manager.read_state()
        if str(current_state.get("operationalState") or "") != "shift_active_running":
            raise HTTPException(status_code=400, detail="KIOSK_WORK_ORDER_START_BLOCKED")
        work_orders = current_state.get("workOrders") if isinstance(current_state.get("workOrders"), dict) else {}
        orders_by_id = work_orders.get("ordersById") if isinstance(work_orders.get("ordersById"), dict) else {}
        queued_order_ids = _queued_order_ids(
            orders_by_id,
            work_orders.get("orderSequence") if isinstance(work_orders.get("orderSequence"), list) else [],
        )
        top_queue_order_id = queued_order_ids[0] if queued_order_ids else ""
        order_id = str(payload.get("order_id") or payload.get("orderId") or "").strip()
        if not order_id:
            order_id = top_queue_order_id
        if not order_id:
            raise HTTPException(status_code=400, detail="WORK_ORDER_NOT_FOUND")
        transition_reason = str(payload.get("transition_reason") or payload.get("transitionReason") or "").strip()
        requested_order = orders_by_id.get(order_id) if isinstance(orders_by_id.get(order_id), dict) else None
        if (
            top_queue_order_id
            and order_id != top_queue_order_id
            and isinstance(requested_order, dict)
            and str(requested_order.get("status") or "").strip() == "queued"
            and not transition_reason
        ):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "KIOSK_QUEUE_REASON_REQUIRED",
                    "requested_order_id": order_id,
                    "priority_order_id": top_queue_order_id,
                },
            )
        try:
            result = oee_state_manager.start_work_order(
                order_id,
                operator_code=actor["operator_code"],
                operator_name=actor["operator_name"],
                transition_reason=transition_reason,
                started_at=str(payload.get("started_at") or payload.get("startedAt") or ""),
            )
        except WorkOrderTransitionReasonRequired as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "WORK_ORDER_REASON_REQUIRED",
                    "order_id": exc.order_id,
                    "previous_order_id": exc.previous_order_id,
                    "elapsed_ms": int(exc.elapsed_ms),
                    "elapsed_minutes": round(exc.elapsed_minutes, 1),
                    "tolerance_ms": int(exc.tolerance_ms),
                    "tolerance_minutes": round(exc.tolerance_minutes, 1),
                },
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc
        stamp = utc_now_text()
        updated_state = result.get("state") if isinstance(result.get("state"), dict) else None
        _refresh_after_kiosk_write(module_id, updated_state)
        order = result.get("order") if isinstance(result.get("order"), dict) else {}
        store.append_system_log(
            module_id,
            f"SYSTEM|KIOSK|WORK_ORDER_START|ORDER={order_id}|OPERATOR={actor['operator_code'] or actor['operator_id']}",
            topic="local/kiosk",
            received_at=stamp,
        )
        return {
            "status": "accepted",
            "summary": str(result.get("summary") or ""),
            "order_id": str(order.get("orderId") or order_id),
        }

    @app.post("/api/modules/{module_id}/kiosk/work-orders/accept-active")
    async def kiosk_accept_active_work_order(module_id: str) -> dict[str, Any]:
        _ensure_module(module_id)
        state = oee_state_manager.read_state()
        active_order_id = str((((state.get("workOrders") or {}) if isinstance(state.get("workOrders"), dict) else {}).get("activeOrderId") or "")).strip()
        active_order = (((state.get("workOrders") or {}) if isinstance(state.get("workOrders"), dict) else {}).get("ordersById") or {}).get(active_order_id) if active_order_id else None
        if not isinstance(active_order, dict) or str(active_order.get("status") or "") != "pending_approval":
            raise HTTPException(status_code=400, detail="ACTIVE_WORK_ORDER_NOT_PENDING_APPROVAL")
        try:
            result = oee_state_manager.accept_active_work_order()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc
        stamp = utc_now_text()
        updated_state = result.get("state") if isinstance(result.get("state"), dict) else None
        _refresh_after_kiosk_write(module_id, updated_state)
        order = result.get("order") if isinstance(result.get("order"), dict) else {}
        store.append_system_log(
            module_id,
            f"SYSTEM|KIOSK|WORK_ORDER_ACCEPT|ORDER={str(order.get('orderId') or '')}",
            topic="local/kiosk",
            received_at=stamp,
        )
        return {
            "status": "accepted",
            "summary": str(result.get("summary") or ""),
            "order_id": str(order.get("orderId") or ""),
        }

    @app.post("/api/modules/{module_id}/kiosk/quality/override")
    async def kiosk_quality_override(module_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        _ensure_module(module_id)
        item_id = str(payload.get("item_id") or payload.get("itemId") or "").strip()
        classification = str(payload.get("classification") or "").strip().upper()
        if not item_id:
            raise HTTPException(status_code=400, detail="INVALID_ITEM_ID")
        try:
            result = oee_state_manager.apply_kiosk_quality_override(
                item_id,
                classification,
                reason_text=str(payload.get("reason_text") or payload.get("reasonText") or ""),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc
        stamp = utc_now_text()
        updated_state = result.get("state") if isinstance(result.get("state"), dict) else None
        _refresh_after_kiosk_write(module_id, updated_state)
        override = result.get("override") if isinstance(result.get("override"), dict) else None
        if override is not None:
            runtime_service.excel_sink.record_quality_override(
                str(override.get("item_id") or item_id),
                str(override.get("classification") or classification),
                str(override.get("applied_at") or stamp),
            )
        store.append_system_log(
            module_id,
            f"SYSTEM|KIOSK|QUALITY_OVERRIDE|ITEM={item_id}|CLASS={classification}",
            topic="local/kiosk",
            received_at=stamp,
        )
        return {
            "status": "accepted",
            "summary": str(result.get("summary") or ""),
            "item_id": item_id,
            "classification": classification,
        }

    @app.post("/api/modules/{module_id}/commands")
    async def publish_command(module_id: str, payload: dict[str, str]) -> dict[str, str]:
        if module_id != config.module_id:
            raise HTTPException(status_code=404, detail="MODULE_NOT_FOUND")

        kind = str(payload.get("kind") or "").strip().lower()
        value = str(payload.get("value") or "").strip()
        if kind not in {"preset", "manual"} or not value:
            raise HTTPException(status_code=400, detail="INVALID_COMMAND_PAYLOAD")

        permissions = store.command_permissions()
        if kind == "preset" and value not in permissions["allowed_presets"]:
            raise HTTPException(status_code=400, detail="UNKNOWN_PRESET_COMMAND")
        if not permissions["publish_enabled"]:
            raise HTTPException(status_code=409, detail="COMMAND_PUBLISH_DISABLED")
        if kind == "manual" and not permissions["manual_command_enabled"]:
            raise HTTPException(status_code=409, detail="MANUAL_COMMAND_DISABLED")

        if is_local_only_command(kind, value):
            stamp = utc_now_text()
            runtime_result: dict[str, Any] | None = None
            try:
                runtime_result = oee_state_manager.reset_runtime_counts()
            except OSError as exc:
                raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc
            store.reset_counts(module_id, received_at=stamp)
            store.refresh_oee_runtime_state(module_id, force=True)
            sync_work_order_runtime(runtime_result.get("state") if isinstance(runtime_result, dict) and isinstance(runtime_result.get("state"), dict) else None)
            runtime_service.excel_sink.record_local_counts_reset(stamp)
            return {"status": "accepted", "kind": kind, "value": value, "dispatch": "local_only"}

        try:
            runtime_service.mqtt_client.publish_command(value)
        except RuntimeError as exc:
            detail = str(exc)
            status_code = 503 if detail.startswith("MQTT_") else 500
            raise HTTPException(status_code=status_code, detail=detail) from exc
        store.append_system_log(module_id, f"SYSTEM|CMD|PUBLISH|KIND={kind.upper()}|VALUE={value}", topic="local/command")

        return {"status": "accepted", "kind": kind, "value": value, "dispatch": "mqtt"}

    @app.post("/api/modules/{module_id}/oee/control")
    async def update_oee_control(module_id: str, payload: dict[str, Any]) -> dict[str, str]:
        if module_id != config.module_id:
            raise HTTPException(status_code=404, detail="MODULE_NOT_FOUND")

        action = str(payload.get("action") or "").strip().lower()
        value = payload.get("value")
        try:
            result = oee_state_manager.apply_control(action, value)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc

        store.refresh_oee_runtime_state(module_id, force=True)
        sync_work_order_runtime(result.get("state") if isinstance(result.get("state"), dict) else None)
        recent_log = str(result.get("recent_log") or "").strip()
        if recent_log:
            store.append_system_log(module_id, recent_log, topic="local/oee")
            runtime_service.excel_sink.record_system_oee_log(recent_log, utc_now_text())

        return {
            "status": "accepted",
            "action": action,
            "summary": str(result.get("summary") or ""),
        }

    @app.post("/api/modules/{module_id}/oee/quality-override")
    async def apply_oee_quality_override(module_id: str, payload: dict[str, Any]) -> dict[str, str]:
        if module_id != config.module_id:
            raise HTTPException(status_code=404, detail="MODULE_NOT_FOUND")

        item_id = str(payload.get("item_id") or "").strip()
        classification = str(payload.get("classification") or "").strip().upper()
        try:
            result = oee_state_manager.apply_quality_override(item_id, classification)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc

        store.refresh_oee_runtime_state(module_id, force=True)
        sync_work_order_runtime(result.get("state") if isinstance(result.get("state"), dict) else None)
        override = result.get("override") if isinstance(result.get("override"), dict) else None
        if override is not None:
            runtime_service.excel_sink.record_quality_override(
                str(override.get("item_id") or item_id),
                str(override.get("classification") or classification),
                str(override.get("applied_at") or utc_now_text()),
            )
        return {
            "status": "accepted",
            "item_id": item_id,
            "classification": classification,
            "summary": str(result.get("summary") or ""),
        }

    @app.post("/api/modules/{module_id}/work-orders/import")
    async def import_work_orders(module_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if module_id != config.module_id:
            raise HTTPException(status_code=404, detail="MODULE_NOT_FOUND")

        orders = payload.get("orders")
        replace_existing = bool(payload.get("replace_existing", True))
        try:
            result = oee_state_manager.import_work_orders(orders, replace_existing=replace_existing)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc

        store.refresh_oee_runtime_state(module_id, force=True)
        sync_work_order_runtime(result.get("state") if isinstance(result.get("state"), dict) else None)
        summary = str(result.get("summary") or "Is emri listesi guncellendi.")
        store.append_system_log(module_id, f"SYSTEM|WORK_ORDER|IMPORT|COUNT={int(result.get('total_count') or 0)}", topic="local/work-orders")
        return {
            "status": "accepted",
            "summary": summary,
            "queued_count": int(result.get("queued_count") or 0),
            "total_count": int(result.get("total_count") or 0),
        }

    @app.post("/api/modules/{module_id}/work-orders/reload")
    async def reload_work_orders(module_id: str) -> dict[str, Any]:
        if module_id != config.module_id:
            raise HTTPException(status_code=404, detail="MODULE_NOT_FOUND")

        candidates = sorted(config.work_orders_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        if not candidates:
            raise HTTPException(status_code=404, detail="WORK_ORDER_SOURCE_NOT_FOUND")
        try:
            result = oee_state_manager.import_work_orders_from_file(candidates[0], replace_existing=True)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc

        store.refresh_oee_runtime_state(module_id, force=True)
        sync_work_order_runtime(result.get("state") if isinstance(result.get("state"), dict) else None)
        summary = str(result.get("summary") or "Is emri kaynagi yenilendi.")
        store.append_system_log(module_id, f"SYSTEM|WORK_ORDER|RELOAD|FILE={candidates[0].name}", topic="local/work-orders")
        return {
            "status": "accepted",
            "summary": summary,
            "source_file": candidates[0].name,
        }

    @app.post("/api/modules/{module_id}/work-orders/tolerance")
    async def update_work_order_tolerance(module_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if module_id != config.module_id:
            raise HTTPException(status_code=404, detail="MODULE_NOT_FOUND")

        try:
            tolerance_value = payload.get("tolerance_ms")
            if tolerance_value in (None, ""):
                tolerance_value = payload.get("minutes", payload.get("tolerance_minutes"))
            else:
                try:
                    tolerance_value = float(tolerance_value) / 60_000.0
                except (TypeError, ValueError) as exc:
                    raise HTTPException(status_code=400, detail="INVALID_TOLERANCE_MS") from exc
            result = oee_state_manager.set_work_order_tolerance(tolerance_value)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc

        store.refresh_oee_runtime_state(module_id, force=True)
        sync_work_order_runtime(result.get("state") if isinstance(result.get("state"), dict) else None)
        summary = str(result.get("summary") or "Is emri toleransi guncellendi.")
        store.append_system_log(module_id, f"SYSTEM|WORK_ORDER|TOLERANCE|{result.get('tolerance_minutes')}", topic="local/work-orders")
        return {
            "status": "accepted",
            "summary": summary,
            "tolerance_ms": int(result.get("tolerance_ms") or 0),
            "tolerance_minutes": float(result.get("tolerance_minutes") or 0.0),
        }

    @app.post("/api/modules/{module_id}/work-orders/reorder")
    async def reorder_work_orders(module_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if module_id != config.module_id:
            raise HTTPException(status_code=404, detail="MODULE_NOT_FOUND")

        try:
            result = oee_state_manager.reorder_work_orders(payload.get("order_ids") or payload.get("orderIds"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc

        store.refresh_oee_runtime_state(module_id, force=True)
        sync_work_order_runtime(result.get("state") if isinstance(result.get("state"), dict) else None)
        summary = str(result.get("summary") or "Is emri sirasi guncellendi.")
        store.append_system_log(module_id, "SYSTEM|WORK_ORDER|REORDER", topic="local/work-orders")
        return {
            "status": "accepted",
            "summary": summary,
        }

    @app.post("/api/modules/{module_id}/work-orders/start")
    async def start_work_order(module_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if module_id != config.module_id:
            raise HTTPException(status_code=404, detail="MODULE_NOT_FOUND")

        try:
            result = oee_state_manager.start_work_order(
                str(payload.get("order_id") or payload.get("orderId") or ""),
                operator_code=str(payload.get("operator_code") or payload.get("operatorCode") or ""),
                operator_name=str(payload.get("operator_name") or payload.get("operatorName") or ""),
                transition_reason=str(payload.get("transition_reason") or payload.get("transitionReason") or ""),
                started_at=str(payload.get("started_at") or payload.get("startedAt") or ""),
            )
        except WorkOrderTransitionReasonRequired as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "WORK_ORDER_REASON_REQUIRED",
                    "order_id": exc.order_id,
                    "previous_order_id": exc.previous_order_id,
                    "elapsed_ms": int(exc.elapsed_ms),
                    "elapsed_minutes": round(exc.elapsed_minutes, 1),
                    "tolerance_ms": int(exc.tolerance_ms),
                    "tolerance_minutes": round(exc.tolerance_minutes, 1),
                },
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc

        store.refresh_oee_runtime_state(module_id, force=True)
        sync_work_order_runtime(result.get("state") if isinstance(result.get("state"), dict) else None)
        order = result.get("order") if isinstance(result.get("order"), dict) else {}
        summary = str(result.get("summary") or "Is emri baslatildi.")
        store.append_system_log(
            module_id,
            f"SYSTEM|WORK_ORDER|START|ORDER={order.get('orderId') or ''}|OPERATOR={order.get('startedBy') or ''}",
            topic="local/work-orders",
        )
        return {
            "status": "accepted",
            "summary": summary,
            "inventory_used": int(result.get("inventory_used") or 0),
            "order_id": str(order.get("orderId") or ""),
        }

    @app.post("/api/modules/{module_id}/work-orders/accept-active")
    async def accept_active_work_order(module_id: str) -> dict[str, Any]:
        if module_id != config.module_id:
            raise HTTPException(status_code=404, detail="MODULE_NOT_FOUND")

        try:
            result = oee_state_manager.accept_active_work_order()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc

        store.refresh_oee_runtime_state(module_id, force=True)
        sync_work_order_runtime(result.get("state") if isinstance(result.get("state"), dict) else None)
        order = result.get("order") if isinstance(result.get("order"), dict) else {}
        summary = str(result.get("summary") or "Is emri operator onayi ile kapatildi.")
        store.append_system_log(
            module_id,
            f"SYSTEM|WORK_ORDER|ACCEPT|ORDER={order.get('orderId') or ''}",
            topic="local/work-orders",
        )
        return {
            "status": "accepted",
            "summary": summary,
            "order_id": str(order.get("orderId") or ""),
        }

    @app.post("/api/modules/{module_id}/work-orders/rollback-active")
    async def rollback_active_work_order(module_id: str) -> dict[str, Any]:
        if module_id != config.module_id:
            raise HTTPException(status_code=404, detail="MODULE_NOT_FOUND")

        try:
            result = oee_state_manager.rollback_active_work_order()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc

        store.refresh_oee_runtime_state(module_id, force=True)
        sync_work_order_runtime(result.get("state") if isinstance(result.get("state"), dict) else None)
        order = result.get("order") if isinstance(result.get("order"), dict) else {}
        summary = str(result.get("summary") or "Aktif is emri geri alindi.")
        store.append_system_log(
            module_id,
            (
                f"SYSTEM|WORK_ORDER|ROLLBACK|ORDER={order.get('orderId') or ''}"
                f"|RETURNED={int(result.get('returned_to_inventory') or 0)}"
            ),
            topic="local/work-orders",
        )
        return {
            "status": "accepted",
            "summary": summary,
            "order_id": str(order.get("orderId") or ""),
            "returned_to_inventory": int(result.get("returned_to_inventory") or 0),
        }

    @app.post("/api/modules/{module_id}/work-orders/reset")
    async def reset_work_orders(module_id: str) -> dict[str, Any]:
        if module_id != config.module_id:
            raise HTTPException(status_code=404, detail="MODULE_NOT_FOUND")

        try:
            result = oee_state_manager.reset_work_orders()
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc

        store.refresh_oee_runtime_state(module_id, force=True)
        sync_work_order_runtime(result.get("state") if isinstance(result.get("state"), dict) else None)
        summary = str(result.get("summary") or "Is emirleri sifirlandi.")
        store.append_system_log(
            module_id,
            f"SYSTEM|WORK_ORDER|RESET|CLEARED={int(result.get('cleared_item_count') or 0)}",
            topic="local/work-orders",
        )
        return {
            "status": "accepted",
            "summary": summary,
            "cleared_item_count": int(result.get("cleared_item_count") or 0),
        }

    @app.post("/api/modules/{module_id}/work-orders/inventory/remove")
    async def remove_inventory_stock(module_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if module_id != config.module_id:
            raise HTTPException(status_code=404, detail="MODULE_NOT_FOUND")

        try:
            result = oee_state_manager.remove_inventory_stock(
                str(payload.get("match_key") or payload.get("matchKey") or ""),
                payload.get("quantity", 1),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc

        store.refresh_oee_runtime_state(module_id, force=True)
        sync_work_order_runtime(result.get("state") if isinstance(result.get("state"), dict) else None)
        summary = str(result.get("summary") or "Depo stogu guncellendi.")
        store.append_system_log(
            module_id,
            (
                f"SYSTEM|WORK_ORDER|INVENTORY_REMOVE|MATCH_KEY={result.get('match_key') or ''}"
                f"|QTY={int(result.get('removed_qty') or 0)}"
            ),
            topic="local/work-orders",
        )
        return {
            "status": "accepted",
            "summary": summary,
            "match_key": str(result.get("match_key") or ""),
            "removed_qty": int(result.get("removed_qty") or 0),
            "remaining_qty": int(result.get("remaining_qty") or 0),
        }

    @app.websocket("/ws/modules/{module_id}/kiosk/{device_id}")
    async def kiosk_stream(websocket: WebSocket, module_id: str, device_id: str) -> None:
        if module_id != config.module_id or not str(device_id or "").strip():
            await websocket.close(code=4404)
            return
        try:
            oee_state_manager.register_kiosk_device(device_id=str(device_id).strip())
            store.refresh_oee_runtime_state(module_id, force=True)
        except OSError:
            pass
        await websocket.accept()
        queue = await hub.register(module_id)
        try:
            await websocket.send_json(
                {
                    "type": "kiosk_snapshot",
                    "module_id": module_id,
                    "device_id": str(device_id).strip(),
                    "data": _build_kiosk_snapshot(module_id, str(device_id).strip()),
                }
            )
            while True:
                await queue.get()
                await websocket.send_json(
                    {
                        "type": "kiosk_snapshot",
                        "module_id": module_id,
                        "device_id": str(device_id).strip(),
                        "data": _build_kiosk_snapshot(module_id, str(device_id).strip()),
                    }
                )
        except WebSocketDisconnect:
            pass
        except OSError as exc:
            if not _is_benign_socket_disconnect_error(exc):
                raise
        finally:
            await hub.unregister(module_id, queue)

    @app.websocket("/ws/modules/{module_id}")
    async def module_stream(websocket: WebSocket, module_id: str) -> None:
        if module_id != config.module_id:
            await websocket.close(code=4404)
            return

        await websocket.accept()
        queue = await hub.register(module_id)
        try:
            await websocket.send_json(
                {
                    "type": "dashboard_snapshot",
                    "module_id": module_id,
                    "data": store.get_dashboard_snapshot(module_id),
                }
            )
            while True:
                message = await queue.get()
                await websocket.send_json(message)
        except WebSocketDisconnect:
            pass
        except OSError as exc:
            if not _is_benign_socket_disconnect_error(exc):
                raise
        finally:
            await hub.unregister(module_id, queue)

    return app


app = create_app()

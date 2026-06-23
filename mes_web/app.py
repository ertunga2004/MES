from __future__ import annotations
import asyncio
import contextlib
import copy
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .command_policy import is_local_only_command
from .config import AppConfig
from .db.package_bom_wip import (
    consume_package_components,
    insufficient_components_detail,
    package_component_availability,
    release_reserved_package_components,
    reserve_package_components,
    reset_demo_package_wip,
)
from .db.package_sessions import (
    upsert_package_session_cancelled,
    upsert_package_session_finished,
    upsert_package_session_started,
)
from .db.health import check_database_health
from .db.mesql_queue import upsert_mesql_queue
from .db.work_order_mirror import load_work_order_planning_snapshot, mirror_work_orders_from_state, reset_work_order_operational_state
from .db.work_order_read import state_with_db_work_orders
from .db.work_order_transition_writer import mirror_work_order_transition_from_state
from .ferp_xls_export import write_seeded_ferp_examples, write_work_order_xls_export
from .masterdata import load_kiosk_masterdata
from .mesql_client import MesqlClient, MesqlConflictError, MesqlError, MesqlUnavailableError, queue_plans
from .oee_state import WorkOrderTransitionReasonRequired, build_work_order_snapshot
from .parsers import normalize_color
from .runtime import RuntimeService, SnapshotHub
from .store import DashboardStore, parse_iso_text, utc_now_text
from .windows_asyncio import install_windows_connection_reset_filter


logger = logging.getLogger(__name__)
config = AppConfig.from_env()
store = DashboardStore(config)
hub = SnapshotHub(store, coalesce_ms=config.ws_coalesce_ms)
runtime_service = RuntimeService(config, store, hub)
oee_state_manager = runtime_service.oee_manager


STATION_BOARD_CONFIG = (
    {"code": "ASSEMBLY_01", "label": "Kutu Uretim"},
    {"code": "PACKAGING_01", "label": "Paketleme"},
)


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


def _queued_order_ids(raw_orders: dict[str, Any], sequence: list[Any], station_code: str = "") -> list[str]:
    queued: list[str] = []
    seen: set[str] = set()

    for raw_order_id in sequence:
        order_id = str(raw_order_id or "").strip()
        order = raw_orders.get(order_id)
        if not order_id or order_id in seen or not isinstance(order, dict):
            continue
        if str(order.get("status") or "").strip() != "queued":
            continue
        if not _order_matches_station(order_id, order, station_code):
            continue
        queued.append(order_id)
        seen.add(order_id)
    for raw_order_id, order in raw_orders.items():
        order_id = str(raw_order_id or "").strip()
        if not order_id or order_id in seen or not isinstance(order, dict):
            continue
        if str(order.get("status") or "").strip() != "queued":
            continue
        if not _order_matches_station(order_id, order, station_code):
            continue
        queued.append(order_id)
        seen.add(order_id)
    return queued


def _order_station_code(order_id: str, order: dict[str, Any]) -> str:
    explicit_station = str(order.get("stationCode") or order.get("station_code") or "").strip().upper()
    if explicit_station:
        return explicit_station
    metadata = order.get("_metadata") if isinstance(order.get("_metadata"), dict) else {}
    metadata_station = str(metadata.get("station_code") or "").strip().upper()
    if metadata_station:
        return metadata_station
    return "PACKAGING_01" if _is_kiosk_package_order(order_id, order) else "ASSEMBLY_01"


def _order_matches_station(order_id: str, order: dict[str, Any], station_code: str = "") -> bool:
    normalized_station = str(station_code or "").strip().upper()
    if not normalized_station:
        return True
    return _order_station_code(order_id, order) == normalized_station


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


def _is_kiosk_package_order(order_id: str, order: dict[str, Any]) -> bool:
    if str(order_id or "").strip().upper().startswith("WO-PKT-"):
        return True
    marker_text = " ".join(
        str(value or "").strip().upper()
        for value in (
            order.get("erpType"),
            order.get("ferpScreen"),
            order.get("stockCode"),
            order.get("stockName"),
            order.get("productCode"),
        )
    )
    return "PAKET" in marker_text or "PACKAGE" in marker_text


def _project_kiosk_packaging(state: dict[str, Any], ordered_orders: list[dict[str, Any]]) -> dict[str, Any]:
    work_orders = state.get("workOrders") if isinstance(state.get("workOrders"), dict) else {}
    buffer = work_orders.get("packagingBuffer") if isinstance(work_orders.get("packagingBuffer"), dict) else {}
    buffer_items = buffer.get("itemsById") if isinstance(buffer.get("itemsById"), dict) else {}
    available_ids = [str(value or "").strip() for value in (buffer.get("availableItemIds") if isinstance(buffer.get("availableItemIds"), list) else [])]
    counts_by_color = {"red": 0, "blue": 0, "yellow": 0}
    projected_items: list[dict[str, Any]] = []
    for item_id, row in buffer_items.items():
        if not isinstance(row, dict):
            continue
        color = _display_color_code(row.get("color"), row.get("product_code"))
        status = str(row.get("status") or "").strip().lower()
        if status == "available" and color in counts_by_color:
            counts_by_color[color] += 1
        projected_items.append(
            {
                "item_id": str(row.get("item_id") or item_id),
                "upstream_order_id": str(row.get("upstream_order_id") or ""),
                "upstream_external_ref": str(row.get("upstream_external_ref") or ""),
                "classification": str(row.get("classification") or ""),
                "product_code": str(row.get("product_code") or ""),
                "color": color,
                "color_label": _display_color_label(color),
                "completed_at": str(row.get("completed_at") or ""),
                "status": status or "available",
                "reserved_by_order_id": str(row.get("reserved_by_order_id") or ""),
                "reserved_by_session_id": str(row.get("reserved_by_session_id") or ""),
            }
        )
    raw_orders = work_orders.get("ordersById") if isinstance(work_orders.get("ordersById"), dict) else {}
    package_orders = []
    for row in ordered_orders:
        order_id = str(row.get("order_id") or "")
        raw_order = raw_orders.get(order_id)
        if not isinstance(raw_order, dict):
            raw_order = {}
        explicit_station = str(raw_order.get("stationCode") or "").strip()
        metadata = raw_order.get("_metadata") if isinstance(raw_order.get("_metadata"), dict) else {}
        if not explicit_station and "station_code" in metadata:
            explicit_station = str(metadata.get("station_code") or "").strip()
        
        is_pkg = False
        if explicit_station == "PACKAGING_01":
            is_pkg = True
        elif explicit_station == "ASSEMBLY_01":
            is_pkg = False
        else:
            is_pkg = _is_kiosk_package_order(order_id, raw_order)
            
        if is_pkg:
            projected_order = copy.deepcopy(row)
            projected_order["package_bom"] = package_component_availability(config, state, projected_order)
            package_orders.append(projected_order)
    sessions = work_orders.get("packagingSessions") if isinstance(work_orders.get("packagingSessions"), dict) else {}
    active_sessions = [
        copy.deepcopy(row)
        for row in sessions.values()
        if isinstance(row, dict) and str(row.get("status") or "").strip().lower() in {"in_progress", "reserved"}
    ]
    return {
        "buffer": {
            "available_item_ids": available_ids,
            "available_count": len(available_ids),
            "counts_by_color": counts_by_color,
            "items": projected_items,
        },
        "package_orders": package_orders,
        "active_sessions": active_sessions,
    }


def _package_wip_summary_from_availability(availability: dict[str, Any]) -> list[dict[str, Any]]:
    components = availability.get("components") if isinstance(availability.get("components"), list) else []
    summary: list[dict[str, Any]] = []
    for component in components:
        if not isinstance(component, dict):
            continue
        required_qty = int(component.get("required_total") or component.get("required_qty") or 0)
        available_qty = int(component.get("available_qty") or 0)
        missing_qty = max(0, required_qty - available_qty)
        summary.append(
            {
                "component_stock_code": str(component.get("component_stock_code") or ""),
                "required_qty": required_qty,
                "available_qty": available_qty,
                "missing_qty": missing_qty,
                "ready": missing_qty <= 0,
                "label": f"{component.get('component_stock_code') or '-'} {available_qty}/{required_qty} {'hazir' if missing_qty <= 0 else 'eksik'}",
            }
        )
    return summary


def _build_station_work_order_board(module_id: str) -> dict[str, Any]:
    state = state_with_db_work_orders(config, oee_state_manager.read_state(), logger=logger).state
    work_orders = state.get("workOrders") if isinstance(state.get("workOrders"), dict) else {}
    raw_orders = work_orders.get("ordersById") if isinstance(work_orders.get("ordersById"), dict) else {}
    sequence = work_orders.get("orderSequence") if isinstance(work_orders.get("orderSequence"), list) else []
    ordered_order_ids: list[str] = []
    seen_order_ids: set[str] = set()
    for raw_order_id in sequence:
        order_id = str(raw_order_id or "").strip()
        if order_id and order_id in raw_orders and order_id not in seen_order_ids:
            ordered_order_ids.append(order_id)
            seen_order_ids.add(order_id)
    for order_id in raw_orders:
        normalized_id = str(order_id or "").strip()
        if normalized_id and normalized_id not in seen_order_ids:
            ordered_order_ids.append(normalized_id)
            seen_order_ids.add(normalized_id)

    projected_by_id: dict[str, dict[str, Any]] = {}
    for order_id in ordered_order_ids:
        order = raw_orders.get(order_id)
        if isinstance(order, dict):
            projected_by_id[order_id] = _project_kiosk_work_order(order_id, order, state)

    stations: dict[str, dict[str, Any]] = {}
    for station in STATION_BOARD_CONFIG:
        station_code = station["code"]
        station_order_ids = [
            order_id
            for order_id in ordered_order_ids
            if isinstance(raw_orders.get(order_id), dict) and _order_matches_station(order_id, raw_orders[order_id], station_code)
        ]
        active_order = None
        pending_order = None
        queue: list[dict[str, Any]] = []
        package_wip_summary: list[dict[str, Any]] = []
        for order_id in station_order_ids:
            projected = copy.deepcopy(projected_by_id.get(order_id) or {})
            raw_order = raw_orders.get(order_id)
            if not projected or not isinstance(raw_order, dict):
                continue
            if station_code == "PACKAGING_01" and _is_kiosk_package_order(order_id, raw_order):
                availability = package_component_availability(config, state, raw_order)
                projected["package_bom"] = availability
                package_sessions = work_orders.get("packagingSessions") if isinstance(work_orders.get("packagingSessions"), dict) else {}
                active_package_session = next(
                    (
                        copy.deepcopy(session)
                        for session in package_sessions.values()
                        if isinstance(session, dict)
                        and str(session.get("package_order_id") or "").strip() == order_id
                        and str(session.get("status") or "").strip().lower() in {"in_progress", "reserved"}
                    ),
                    None,
                )
                projected["package_session"] = active_package_session
                projected["package_process_status"] = str((active_package_session or {}).get("status") or "not_started").strip().lower()
                if not package_wip_summary:
                    package_wip_summary = _package_wip_summary_from_availability(availability)
            status = str(projected.get("status") or "").strip()
            if status == "active" and active_order is None:
                active_order = projected
            elif status == "pending_approval" and pending_order is None:
                pending_order = projected
            elif status == "queued":
                queue.append(projected)
        stations[station_code] = {
            "station_code": station_code,
            "station_label": station["label"],
            "active_order": active_order,
            "pending_order": pending_order,
            "queue": queue,
            "queue_order_ids": [str(row.get("order_id") or "") for row in queue],
            "package_wip_summary": package_wip_summary,
            "updated_at": str(state.get("lastUpdatedAt") or ""),
        }
    return stations


def _build_dashboard_snapshot(module_id: str) -> dict[str, Any]:
    snapshot = copy.deepcopy(store.get_dashboard_snapshot(module_id))
    snapshot["station_work_orders"] = _build_station_work_order_board(module_id)
    state = oee_state_manager.read_state()
    snapshot["integrations"] = copy.deepcopy(state.get("integrations") if isinstance(state.get("integrations"), dict) else {})
    return snapshot


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
    packaging: dict[str, Any] | None = None,
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
        if _is_kiosk_package_order(str(active_order.get("order_id") or ""), active_order):
            active_sessions = packaging.get("active_sessions", []) if isinstance(packaging, dict) else []
            my_session = next((s for s in active_sessions if str(s.get("package_order_id") or "") == str(active_order.get("order_id") or "")), None)
            if my_session:
                return {
                    "action": "package_finish",
                    "label": "Paketlemeyi Bitir",
                    "enabled": True,
                    "phase": "",
                    "payload": {"session_id": str(my_session.get("session_id") or "")}
                }
            return {
                "action": "package_start",
                "label": "Paketlemeye Basla",
                "enabled": True,
                "phase": "",
                "payload": {"package_order_id": str(active_order.get("order_id") or "")}
            }

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


def _build_kiosk_snapshot(module_id: str, device_id: str, station_code: str = "") -> dict[str, Any]:
    dashboard = store.get_dashboard_snapshot(module_id)
    state = state_with_db_work_orders(config, oee_state_manager.read_state(), logger=logger).state
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
    queued_order_ids = _queued_order_ids(raw_orders, sequence, station_code=station_code)
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
        
    filtered_orders = []
    for row in ordered_orders:
        order_id = str(row.get("order_id") or "")
        raw_order = raw_orders.get(order_id)
        if not isinstance(raw_order, dict):
            raw_order = {}
            
        explicit_station = str(raw_order.get("stationCode") or "").strip()
        metadata = raw_order.get("_metadata") if isinstance(raw_order.get("_metadata"), dict) else {}
        if not explicit_station and "station_code" in metadata:
            explicit_station = str(metadata.get("station_code") or "").strip()
            
        is_pkg = False
        if explicit_station == "PACKAGING_01":
            is_pkg = True
        elif explicit_station == "ASSEMBLY_01":
            is_pkg = False
        else:
            is_pkg = _is_kiosk_package_order(order_id, raw_order)

        if station_code == "PACKAGING_01":
            if is_pkg:
                filtered_orders.append(row)
        elif station_code == "ASSEMBLY_01":
            if not is_pkg:
                filtered_orders.append(row)
        else:
            filtered_orders.append(row)
    ordered_orders = filtered_orders

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
    packaging_state = _project_kiosk_packaging(state, ordered_orders)
    return {
        "station_context": {
            "station_code": station_code
        },
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
        "packaging": packaging_state,
        "recent_items": recent_items,
        "quality_options": ["GOOD", "REWORK", "SCRAP"],
        "integrations": copy.deepcopy(state.get("integrations") if isinstance(state.get("integrations"), dict) else {}),
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
            packaging=packaging_state,
        ),
        "timestamps": {
            "snapshot_at": utc_now_text(),
            "last_updated_at": state.get("lastUpdatedAt"),
        },
    }


def _duration_ms_between(start_value: Any, end_value: Any) -> int:
    start_at = parse_iso_text(str(start_value or ""))
    if isinstance(end_value, datetime):
        end_at = end_value.astimezone()
    else:
        end_at = parse_iso_text(str(end_value or ""))
    if start_at is None or end_at is None or end_at < start_at:
        return 0
    return max(0, int((end_at - start_at).total_seconds() * 1000))


def _duration_text(duration_ms: Any) -> str:
    total_seconds = max(0, int(float(duration_ms or 0) // 1000))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _request_event_at(row: dict[str, Any]) -> datetime | None:
    candidates = [
        parse_iso_text(str(row.get("resolvedAt") or "")),
        parse_iso_text(str(row.get("acknowledgedAt") or "")),
        parse_iso_text(str(row.get("lastRequestedAt") or "")),
        parse_iso_text(str(row.get("createdAt") or "")),
    ]
    parsed = [candidate for candidate in candidates if candidate is not None]
    return max(parsed) if parsed else None


def _sort_floor_datetime() -> datetime:
    return datetime(1970, 1, 1, tzinfo=timezone.utc)


def _sort_ceiling_datetime() -> datetime:
    return datetime(9999, 12, 31, tzinfo=timezone.utc)


def _active_fault_matches_request(active_fault: dict[str, Any] | None, row: dict[str, Any]) -> bool:
    if not isinstance(active_fault, dict):
        return False
    request_fault_id = str(row.get("faultId") or "").strip()
    active_fault_id = str(active_fault.get("faultId") or "").strip()
    if request_fault_id and active_fault_id and request_fault_id == active_fault_id:
        return True
    request_device_id = str(row.get("deviceId") or "").strip()
    active_device_id = str(active_fault.get("deviceId") or "").strip()
    request_station_id = str(row.get("boundStationId") or "").strip()
    active_station_id = str(active_fault.get("boundStationId") or "").strip()
    return bool(
        (request_device_id and active_device_id and request_device_id == active_device_id)
        or (request_station_id and active_station_id and request_station_id == active_station_id)
    )


def _project_technician_request(
    row: dict[str, Any],
    *,
    catalog: dict[str, Any],
    active_fault: dict[str, Any] | None,
    now: datetime,
) -> dict[str, Any]:
    status = str(row.get("status") or "open").strip() or "open"
    station = _catalog_station(catalog, row.get("boundStationId"))
    station_id = str(row.get("boundStationId") or "").strip()
    station_name = (
        str(row.get("stationName") or "").strip()
        or str((station or {}).get("station_name_tr") or "").strip()
        or str((station or {}).get("station_code") or "").strip()
        or station_id
    )
    line_id = str(row.get("lineId") or "").strip() or str((station or {}).get("line_id") or "").strip()
    created_at = str(row.get("createdAt") or "")
    acknowledged_at = str(row.get("acknowledgedAt") or "")
    resolved_at = str(row.get("resolvedAt") or "")
    response_duration_ms = int(row.get("responseDurationMs") or 0)
    repair_duration_ms = int(row.get("repairDurationMs") or 0)
    total_duration_ms = int(row.get("totalDurationMs") or 0)
    if status == "open":
        response_duration_ms = _duration_ms_between(created_at, now)
        repair_duration_ms = 0
        total_duration_ms = response_duration_ms
    elif status == "acknowledged":
        response_duration_ms = response_duration_ms or _duration_ms_between(created_at, acknowledged_at)
        repair_duration_ms = _duration_ms_between(acknowledged_at, now)
        total_duration_ms = _duration_ms_between(created_at, now)
    else:
        response_duration_ms = response_duration_ms or _duration_ms_between(created_at, acknowledged_at)
        repair_duration_ms = repair_duration_ms or _duration_ms_between(acknowledged_at, resolved_at)
        total_duration_ms = total_duration_ms or _duration_ms_between(created_at, resolved_at)
    reason = str(row.get("reason") or "").strip()
    if not reason and _active_fault_matches_request(active_fault, row):
        reason = str((active_fault or {}).get("reason") or "").strip()
    fault_code = str(row.get("faultCode") or "").strip()
    if not fault_code and _active_fault_matches_request(active_fault, row):
        fault_code = str((active_fault or {}).get("reasonCode") or "").strip()
    fault_started_at = str(row.get("faultStartedAt") or "").strip()
    if not fault_started_at and _active_fault_matches_request(active_fault, row):
        fault_started_at = str((active_fault or {}).get("startedAt") or "").strip()
    return {
        "request_id": str(row.get("requestId") or ""),
        "status": status,
        "repeat_count": int(row.get("repeatCount") or 1),
        "line_id": line_id,
        "station_id": station_id,
        "station_name": station_name,
        "device_id": str(row.get("deviceId") or ""),
        "device_name": str(row.get("deviceName") or row.get("deviceId") or ""),
        "operator_id": str(row.get("operatorId") or ""),
        "operator_code": str(row.get("operatorCode") or ""),
        "operator_name": str(row.get("operatorName") or ""),
        "fault_id": str(row.get("faultId") or ""),
        "fault_code": fault_code,
        "reason": reason,
        "fault_started_at": fault_started_at,
        "created_at": created_at,
        "last_requested_at": str(row.get("lastRequestedAt") or ""),
        "acknowledged_at": acknowledged_at,
        "resolved_at": resolved_at,
        "technician_name": str(row.get("technicianName") or ""),
        "response_duration_ms": response_duration_ms,
        "repair_duration_ms": repair_duration_ms,
        "total_duration_ms": total_duration_ms,
        "response_duration_text": _duration_text(response_duration_ms),
        "repair_duration_text": _duration_text(repair_duration_ms),
        "total_duration_text": _duration_text(total_duration_ms),
        "is_active_fault": _active_fault_matches_request(active_fault, row),
    }


def _build_technician_snapshot(module_id: str, device_id: str, technician_name: str = "") -> dict[str, Any]:
    state = oee_state_manager.read_state()
    catalog = load_kiosk_masterdata(config)
    now = datetime.now().astimezone()
    help_request = state.get("helpRequest") if isinstance(state.get("helpRequest"), dict) else {}
    requests_by_key = help_request.get("requestsByKey") if isinstance(help_request.get("requestsByKey"), dict) else {}
    history = help_request.get("history") if isinstance(help_request.get("history"), list) else []
    latest_by_id: dict[str, dict[str, Any]] = {}
    latest_rank: dict[str, datetime] = {}
    for raw_row in list(requests_by_key.values()) + [row for row in history if isinstance(row, dict)]:
        if not isinstance(raw_row, dict):
            continue
        request_id = str(raw_row.get("requestId") or "").strip()
        if not request_id:
            continue
        event_at = _request_event_at(raw_row) or _sort_floor_datetime()
        if request_id not in latest_by_id or event_at >= latest_rank[request_id]:
            latest_by_id[request_id] = raw_row
            latest_rank[request_id] = event_at
    active_fault = state.get("activeFault") if isinstance(state.get("activeFault"), dict) else None
    projected = [
        _project_technician_request(row, catalog=catalog, active_fault=active_fault, now=now)
        for row in latest_by_id.values()
    ]
    projected.sort(
        key=lambda row: (
            parse_iso_text(str(row.get("resolved_at") or row.get("acknowledged_at") or row.get("last_requested_at") or row.get("created_at") or ""))
            or _sort_floor_datetime()
        ),
        reverse=True,
    )
    active_requests = [
        row
        for row in projected
        if str(row.get("status") or "") in {"open", "acknowledged"}
    ]
    active_requests.sort(
        key=lambda row: (
            0 if str(row.get("status") or "") == "open" else 1,
            parse_iso_text(str(row.get("created_at") or "")) or _sort_ceiling_datetime(),
        )
    )
    today = now.date()
    resolved_today = [
        row
        for row in projected
        if str(row.get("status") or "") == "resolved"
        and (parse_iso_text(str(row.get("resolved_at") or "")) or _sort_floor_datetime()).astimezone().date() == today
    ]
    recent_requests = projected[:10]
    device_registry = state.get("deviceRegistry") if isinstance(state.get("deviceRegistry"), dict) else {}
    device_entry = device_registry.get(device_id) if isinstance(device_registry.get(device_id), dict) else {}
    open_count = sum(1 for row in active_requests if str(row.get("status") or "") == "open")
    acknowledged_count = sum(1 for row in active_requests if str(row.get("status") or "") == "acknowledged")
    return {
        "module": {
            "module_id": module_id,
            "title": config.module_title,
            "snapshot_at": utc_now_text(now),
        },
        "device": {
            "device_id": device_id,
            "device_name": str(device_entry.get("deviceName") or device_id),
            "device_role": str(device_entry.get("deviceRole") or "technician_kiosk"),
            "last_seen_at": device_entry.get("lastSeenAt"),
        },
        "technician": {
            "technician_name": str(technician_name or "").strip(),
        },
        "summary": {
            "open_count": open_count,
            "acknowledged_count": acknowledged_count,
            "resolved_today_count": len(resolved_today),
            "recent_count": len(recent_requests),
        },
        "active_requests": copy.deepcopy(active_requests),
        "resolved_today": copy.deepcopy(resolved_today),
        "recent_requests": copy.deepcopy(recent_requests),
    }


def create_app() -> FastAPI:
    app = FastAPI(title="MES Web", version="0.1.0")
    static_dir = Path(config.static_dir)
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    mesql_client = MesqlClient(config.mesql_api_base_url, timeout_sec=config.mesql_timeout_sec)
    mesql_refresh_task: asyncio.Task[None] | None = None

    def sync_work_order_runtime(
        state: dict[str, Any] | None = None,
        *,
        event_type: str = "runtime_sync",
        actor_id: str = "",
        replace_current: bool = False,
        mirror_current: bool = True,
    ) -> Any:
        runtime_state = state if isinstance(state, dict) else oee_state_manager.read_state()
        runtime_service.excel_sink.record_work_order_state(runtime_state, utc_now_text())
        try:
            transition_result = mirror_work_order_transition_from_state(
                config,
                runtime_state,
                event_type=event_type,
                actor_id=actor_id,
                replace_current=replace_current,
            )
        except Exception:
            logger.exception("Work order DB transition hook failed unexpectedly")
            transition_result = None
        if transition_result is not None and transition_result.reason == "error_fail_open":
            logger.warning("Work order DB transition hook failed open: %s", transition_result.error_type)
        if mirror_current:
            try:
                mirror_result = mirror_work_orders_from_state(config, runtime_state)
            except Exception:
                logger.exception("Work order DB mirror hook failed unexpectedly")
            else:
                if mirror_result.status == "error":
                    logger.warning("Work order DB mirror failed: %s", mirror_result.message)
        store.refresh_oee_runtime_state(config.module_id, force=True)
        return transition_result

    def _ferp_export_acceptance_result(result: dict[str, Any]) -> dict[str, Any]:
        try:
            order = result.get("order") if isinstance(result.get("order"), dict) else {}
            example_files = write_seeded_ferp_examples(config.ferp_xls_dir, config.ferp_export_examples_dir)
            export = write_work_order_xls_export(
                order,
                source_dir=config.ferp_xls_dir,
                pending_dir=config.ferp_export_pending_dir,
            )
            return {
                "status": "pending",
                "export_id": export.export_id,
                "directory": str(export.directory),
                "files": [str(path) for path in export.files],
                "example_files": [str(path) for path in example_files],
                "warnings": list(export.warnings),
            }
        except Exception as exc:
            return {
                "status": "error",
                "message": str(exc),
            }

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

    def _optional_kiosk_actor(payload: dict[str, Any]) -> dict[str, str]:
        has_actor_context = any(
            str(payload.get(key) or "").strip()
            for key in (
                "device_id",
                "deviceId",
                "operator_id",
                "operatorId",
                "operator_code",
                "operatorCode",
                "bound_station_id",
                "boundStationId",
            )
        )
        if has_actor_context:
            return _resolve_kiosk_actor(payload)
        return {
            "device_id": "",
            "device_name": "",
            "device_role": "operator_kiosk",
            "bound_station_id": "",
            "operator_id": "",
            "operator_code": "",
            "operator_name": "",
        }

    def _station_context_for_actor(actor: dict[str, str]) -> dict[str, str]:
        catalog = load_kiosk_masterdata(config)
        station = _catalog_station(catalog, actor.get("bound_station_id"))
        return {
            "line_id": str((station or {}).get("line_id") or ""),
            "station_name": str((station or {}).get("station_name_tr") or (station or {}).get("station_code") or ""),
        }

    def _resolve_technician_actor(payload: dict[str, Any]) -> dict[str, str]:
        device_id = str(payload.get("device_id") or payload.get("deviceId") or "").strip()
        device_name = str(payload.get("device_name") or payload.get("deviceName") or device_id or "Teknisyen Ekrani").strip()
        technician_name = str(payload.get("technician_name") or payload.get("technicianName") or "").strip() or "Teknisyen"
        return {
            "device_id": device_id,
            "device_name": device_name,
            "technician_name": technician_name,
        }

    def _record_kiosk_event(event_type: str, payload: dict[str, Any], *, received_at: str) -> None:
        runtime_service.excel_sink.record_kiosk_event(event_type, payload, received_at)

    def _refresh_after_kiosk_write(
        module_id: str,
        state: dict[str, Any] | None,
        *,
        event_type: str = "runtime_sync",
        actor_id: str = "",
        replace_current: bool = False,
    ) -> Any:
        store.refresh_oee_runtime_state(module_id, force=True)
        return sync_work_order_runtime(state, event_type=event_type, actor_id=actor_id, replace_current=replace_current)

    def _mesql_detail(code: str, message: str, **extra: Any) -> dict[str, Any]:
        return {"code": code, "message": message, **extra}

    def _reject_mesql_unsupported(action: str) -> None:
        if config.mesql_enabled:
            raise HTTPException(
                status_code=409,
                detail=_mesql_detail(
                    "MESQL_ACTION_UNSUPPORTED",
                    f"{action} islemi Faz 1 MESQL kontratinda desteklenmiyor.",
                ),
            )

    def _raise_mesql_error(exc: MesqlError) -> None:
        status_code = 503 if isinstance(exc, MesqlUnavailableError) else (exc.status_code or 502)
        raise HTTPException(
            status_code=status_code,
            detail=_mesql_detail(exc.code, exc.message, remote_detail=exc.detail),
        ) from exc

    def _require_mesql_local_db() -> None:
        if not config.db_enabled or not config.db_hook_work_order_transitions:
            raise HTTPException(
                status_code=503,
                detail=_mesql_detail(
                    "MES_LOCAL_DB_NOT_READY",
                    "MESQL islemi icin kalici MES DB ve work-order transition hook acik olmalidir.",
                ),
            )
        health = check_database_health(config)
        if str(health.get("status") or "") != "ok":
            raise HTTPException(
                status_code=503,
                detail=_mesql_detail("MES_LOCAL_DB_UNAVAILABLE", "Kalici MES veritabanina ulasilamiyor."),
            )

    async def _sync_mesql_queue(station_code: str, *, include_done: bool = False, required: bool = False) -> list[Any]:
        if not config.mesql_enabled:
            return []
        normalized_station = str(station_code or "").strip().upper()
        if not normalized_station:
            if required:
                raise HTTPException(status_code=400, detail="WORK_ORDER_STATION_REQUIRED")
            return []
        try:
            payload = await mesql_client.get_station_queue(normalized_station, include_done=include_done)
            plans = queue_plans(payload, station_code=normalized_station)
        except MesqlError as exc:
            with contextlib.suppress(OSError):
                oee_state_manager.set_mesql_status("unavailable", error=exc.message)
            if required:
                _raise_mesql_error(exc)
            return []
        write_result = upsert_mesql_queue(config, plans)
        if not write_result.success:
            error_suffix = f" ({write_result.error_type})" if write_result.error_type else ""
            message = f"MESQL queue yerel DB'ye yazilamadi: {write_result.reason}{error_suffix}"
            with contextlib.suppress(OSError):
                oee_state_manager.set_mesql_status("unavailable", error=message)
            if required:
                raise HTTPException(
                    status_code=503,
                    detail=_mesql_detail(
                        "MES_LOCAL_DB_QUEUE_WRITE_FAILED",
                        message,
                        db_error_type=write_result.error_type,
                        db_error_message=write_result.error_message,
                    ),
                )
            return []
        try:
            oee_state_manager.merge_mesql_queue_plans(plans)
        except OSError as exc:
            if required:
                raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc
            return []
        store.refresh_oee_runtime_state(config.module_id, force=True)
        return plans

    async def _mesql_refresh_loop() -> None:
        while True:
            for station_code in config.mesql_station_codes:
                await _sync_mesql_queue(station_code)
            await asyncio.sleep(max(1.0, config.mesql_queue_refresh_sec))

    def _queue_plan_for_order(plans: list[Any], order_id: str, station_code: str) -> Any | None:
        normalized_order = str(order_id or "").strip()
        normalized_station = str(station_code or "").strip().upper()
        return next(
            (
                plan
                for plan in plans
                if plan.order_id == normalized_order and plan.station_code == normalized_station
            ),
            None,
        )

    def _local_work_order_context(order_id: str, station_code: str) -> tuple[str, str]:
        normalized_order = str(order_id or "").strip()
        normalized_station = str(station_code or "").strip().upper()
        state = oee_state_manager.read_state()
        work_orders = state.get("workOrders") if isinstance(state.get("workOrders"), dict) else {}
        if not normalized_order:
            normalized_order = str(work_orders.get("activeOrderId") or "").strip()
        orders_by_id = work_orders.get("ordersById") if isinstance(work_orders.get("ordersById"), dict) else {}
        order = orders_by_id.get(normalized_order) if isinstance(orders_by_id.get(normalized_order), dict) else {}
        if not normalized_station:
            metadata = order.get("_metadata") if isinstance(order.get("_metadata"), dict) else {}
            mesql_metadata = order.get("_mesql") if isinstance(order.get("_mesql"), dict) else {}
            normalized_station = str(
                order.get("stationCode")
                or order.get("workStationCode")
                or metadata.get("station_code")
                or mesql_metadata.get("station_code")
                or ""
            ).strip().upper()
        return normalized_order, normalized_station

    def _operation_no(order: dict[str, Any], plan: Any | None = None) -> int:
        raw = getattr(plan, "operation_no", None) if plan is not None else None
        if raw in (None, ""):
            raw = order.get("operationNo")
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = 0
        if value <= 0:
            raise HTTPException(status_code=400, detail=_mesql_detail("MESQL_OPERATION_NO_REQUIRED", "MESQL operation_no bulunamadi."))
        return value

    def _mark_reconciliation(action: str, *, order_id: str, operation_no: int, station_code: str, remote: dict[str, Any], error: BaseException) -> None:
        action_key = f"{action}:{order_id}:{operation_no}"
        payload = {
            "action": action,
            "order_id": order_id,
            "operation_no": operation_no,
            "station_code": station_code,
            "recorded_at": utc_now_text(),
            "remote": copy.deepcopy(remote),
            "local_error": f"{type(error).__name__}: {error}",
        }
        logger.error("MESQL reconciliation required: %s", payload)
        with contextlib.suppress(OSError):
            oee_state_manager.mark_mesql_reconciliation_required(action_key, payload)

    def _pending_reconciliation(action: str, order_id: str, station_code: str) -> tuple[str, dict[str, Any]] | None:
        state = oee_state_manager.read_state()
        mesql = ((state.get("integrations") or {}).get("mesql") if isinstance(state.get("integrations"), dict) else {}) or {}
        rows = mesql.get("reconciliationRequired") if isinstance(mesql.get("reconciliationRequired"), dict) else {}
        for action_key, raw in rows.items():
            if not isinstance(raw, dict):
                continue
            if str(raw.get("action") or "") != action or str(raw.get("order_id") or "") != order_id:
                continue
            record_station = str(raw.get("station_code") or "").strip().upper()
            if station_code and record_station and record_station != station_code:
                continue
            return str(action_key), raw
        return None

    def _reconcile_local_transition(
        action: str,
        *,
        action_key: str,
        order_id: str,
        station_code: str,
        plan: Any,
        actor_id: str,
    ) -> dict[str, Any]:
        state = oee_state_manager.read_state()
        work_orders = state.get("workOrders") if isinstance(state.get("workOrders"), dict) else {}
        orders = work_orders.get("ordersById") if isinstance(work_orders.get("ordersById"), dict) else {}
        order = orders.get(order_id) if isinstance(orders.get(order_id), dict) else {}
        local_status = str(order.get("status") or "").lower()
        remote_status = {
            str(getattr(plan, "remote_order_status", "") or "").lower(),
            str(getattr(plan, "remote_queue_status", "") or "").lower(),
        }
        if action == "start":
            confirmed = local_status == "active" and bool(remote_status & {"started", "in_progress", "active"})
            event_type = "started"
        else:
            confirmed = local_status == "completed" and bool(remote_status & {"completed", "done"})
            event_type = "completed"
            snapshot = build_work_order_snapshot(state, order)
            remote_good = getattr(plan, "remote_good_quantity", None)
            remote_scrap = getattr(plan, "remote_scrap_quantity", None)
            confirmed = confirmed and remote_good is not None and remote_scrap is not None
            if confirmed and (
                abs(float(remote_good) - float(snapshot.get("goodQty") or 0)) > 1e-9
                or abs(float(remote_scrap) - float(snapshot.get("scrapQty") or 0)) > 1e-9
            ):
                raise HTTPException(
                    status_code=409,
                    detail=_mesql_detail(
                        "MESQL_COMPLETION_QUANTITY_MISMATCH",
                        "MESQL tamamlanma miktarlari yerel GOOD/SCRAP degerleriyle eslesmiyor.",
                    ),
                )
        if not confirmed:
            raise HTTPException(
                status_code=409,
                detail=_mesql_detail(
                    "MESQL_RECONCILIATION_NOT_CONFIRMED",
                    "Merkezi MESQL durumu yerel reconciliation icin dogrulanamadi.",
                ),
            )
        transition_result = sync_work_order_runtime(state, event_type=event_type, actor_id=actor_id)
        try:
            _ensure_local_transition_written(transition_result)
        except RuntimeError as exc:
            _mark_reconciliation(action, order_id=order_id, operation_no=_operation_no(order, plan), station_code=station_code, remote={"status": next(iter(remote_status), "")}, error=exc)
            raise HTTPException(
                status_code=500,
                detail=_mesql_detail("MESQL_RECONCILIATION_REQUIRED", "Yerel DB reconciliation tekrar basarisiz oldu."),
            ) from exc
        oee_state_manager.clear_mesql_reconciliation_required(action_key)
        store.refresh_oee_runtime_state(config.module_id, force=True)
        return {
            "status": "accepted",
            "summary": f"{order_id} yerel MES DB ile uzlastirildi.",
            "order_id": order_id,
            "reconciled": True,
        }

    def _ensure_local_transition_written(result: Any) -> None:
        if result is None or not bool(getattr(result, "success", False)):
            reason = str(getattr(result, "reason", "missing_result"))
            raise RuntimeError(f"LOCAL_DB_TRANSITION_FAILED:{reason}")

    def _remote_status_tokens(value: Any) -> set[str]:
        if isinstance(value, dict):
            values = [value.get("status"), value.get("message"), value.get("code")]
        else:
            values = [value]
        return {str(item or "").strip().lower() for item in values if str(item or "").strip()}

    async def _call_mesql_start(
        self_order_id: str,
        *,
        operation_no: int,
        operator_id: str,
        station_code: str,
        started_at: str,
    ) -> dict[str, Any]:
        try:
            return await mesql_client.start_operation(
                order_id=self_order_id,
                operation_no=operation_no,
                operator_id=operator_id,
                station_code=station_code,
                started_at=started_at,
            )
        except MesqlConflictError as exc:
            tokens = _remote_status_tokens(exc.detail)
            possible_idempotent = any(token in {"already_started", "started", "in_progress", "active"} for token in tokens)
            if possible_idempotent:
                plans = await _sync_mesql_queue(station_code, required=True)
                plan = _queue_plan_for_order(plans, self_order_id, station_code)
                remote_tokens = {
                    str(getattr(plan, "remote_order_status", "") or "").lower(),
                    str(getattr(plan, "remote_queue_status", "") or "").lower(),
                }
                if plan is not None and remote_tokens & {"started", "in_progress", "active"}:
                    return {"status": "in_progress", "idempotent": True}
            _raise_mesql_error(exc)
        except MesqlError as exc:
            _raise_mesql_error(exc)
        raise AssertionError("unreachable")

    async def _call_mesql_complete(
        self_order_id: str,
        *,
        operation_no: int,
        operator_id: str,
        station_code: str,
        good_quantity: float,
        scrap_quantity: float,
        uom_code: str,
        completed_at: str,
    ) -> dict[str, Any]:
        try:
            return await mesql_client.complete_operation(
                order_id=self_order_id,
                operation_no=operation_no,
                operator_id=operator_id,
                station_code=station_code,
                good_quantity=good_quantity,
                scrap_quantity=scrap_quantity,
                uom_code=uom_code,
                completed_at=completed_at,
            )
        except MesqlConflictError as exc:
            tokens = _remote_status_tokens(exc.detail)
            if "already_completed" in tokens:
                plans = await _sync_mesql_queue(station_code, include_done=True, required=True)
                plan = _queue_plan_for_order(plans, self_order_id, station_code)
                if plan is not None:
                    remote_status = {
                        str(plan.remote_order_status or "").lower(),
                        str(plan.remote_queue_status or "").lower(),
                    }
                    if remote_status & {"completed", "done"}:
                        remote_good = getattr(plan, "remote_good_quantity", None)
                        remote_scrap = getattr(plan, "remote_scrap_quantity", None)
                        if remote_good is None or remote_scrap is None or abs(float(remote_good) - good_quantity) > 1e-9 or abs(float(remote_scrap) - scrap_quantity) > 1e-9:
                            raise HTTPException(
                                status_code=409,
                                detail=_mesql_detail(
                                    "MESQL_COMPLETION_QUANTITY_MISMATCH",
                                    "MESQL tamamlanma miktarlari yerel GOOD/SCRAP degerleriyle eslesmiyor.",
                                ),
                            ) from exc
                        return {"status": "completed", "idempotent": True}
            _raise_mesql_error(exc)
        except MesqlError as exc:
            _raise_mesql_error(exc)
        raise AssertionError("unreachable")

    @app.on_event("startup")
    async def on_startup() -> None:
        nonlocal mesql_refresh_task
        install_windows_connection_reset_filter()
        await runtime_service.start()
        if config.mesql_enabled:
            mesql_refresh_task = asyncio.create_task(_mesql_refresh_loop())

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        if mesql_refresh_task is not None:
            mesql_refresh_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await mesql_refresh_task
        await runtime_service.stop()

    @app.get("/health")
    async def health() -> dict[str, Any]:
        if not config.mesql_enabled:
            return {"status": "ok", "time": utc_now_text()}
        state = oee_state_manager.read_state()
        mesql = ((state.get("integrations") or {}).get("mesql") if isinstance(state.get("integrations"), dict) else {}) or {}
        degraded = config.mesql_enabled and str(mesql.get("status") or "") not in {"ok"}
        return {"status": "degraded" if degraded else "ok", "time": utc_now_text(), "mesql": copy.deepcopy(mesql)}

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

    @app.get("/kiosk/")
    async def kiosk_selector() -> HTMLResponse:
        html_content = """
        <!doctype html>
        <html lang="tr">
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <title>MES Station Selector</title>
          <link rel="stylesheet" href="/static/kiosk.css">
        </head>
        <body class="selector-body" style="padding:2rem;font-family:sans-serif;background:#f5f5f5;">
          <div class="selector-container" style="max-width:600px;margin:0 auto;background:#fff;padding:2rem;border-radius:8px;box-shadow:0 4px 6px rgba(0,0,0,0.1);">
            <h1 style="margin-top:0;">Istasyon Seciniz</h1>
            <div class="selector-cards" style="display:flex;flex-direction:column;gap:1rem;margin-top:1.5rem;">
              <a href="/kiosk/station/ASSEMBLY_01" class="station-card" style="text-decoration:none;color:inherit;border:1px solid #ddd;padding:1.5rem;border-radius:6px;display:block;transition:all 0.2s;">
                <h2 style="margin:0 0 0.5rem 0;color:#0052cc;">ASSEMBLY_01</h2>
                <p style="margin:0;color:#555;">Istasyon 1 - Kutu Uretim</p>
              </a>
              <a href="/kiosk/station/PACKAGING_01" class="station-card" style="text-decoration:none;color:inherit;border:1px solid #ddd;padding:1.5rem;border-radius:6px;display:block;transition:all 0.2s;">
                <h2 style="margin:0 0 0.5rem 0;color:#0052cc;">PACKAGING_01</h2>
                <p style="margin:0;color:#555;">Istasyon 2 - Paketleme</p>
              </a>
            </div>
          </div>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content)

    @app.get("/kiosk/station/{station_code}")
    async def kiosk_station_index(station_code: str) -> FileResponse:
        if not str(station_code or "").strip():
            raise HTTPException(status_code=400, detail="STATION_CODE_REQUIRED")
        return FileResponse(
            static_dir / "kiosk.html",
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

    @app.get("/technician/{device_id}")
    async def technician_index(device_id: str) -> FileResponse:
        if not str(device_id or "").strip():
            raise HTTPException(status_code=400, detail="DEVICE_ID_REQUIRED")
        return FileResponse(
            static_dir / "technician.html",
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
            if config.mesql_enabled:
                for station_code in config.mesql_station_codes:
                    await _sync_mesql_queue(station_code)
            return _build_dashboard_snapshot(module_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="MODULE_NOT_FOUND") from exc

    @app.get("/api/modules/{module_id}/kiosk/bootstrap")
    async def get_kiosk_bootstrap(module_id: str, device_id: str, station_code: str = "") -> dict[str, Any]:
        _ensure_module(module_id)
        if not str(device_id or "").strip():
            raise HTTPException(status_code=400, detail="DEVICE_ID_REQUIRED")
        if config.mesql_enabled:
            await _sync_mesql_queue(station_code or config.mesql_station_codes[0])
        store.refresh_oee_runtime_state(module_id, force=True)
        return _build_kiosk_snapshot(module_id, str(device_id).strip(), station_code)

    @app.get("/api/modules/{module_id}/technician/bootstrap")
    async def get_technician_bootstrap(module_id: str, device_id: str, technician_name: str = "") -> dict[str, Any]:
        _ensure_module(module_id)
        if not str(device_id or "").strip():
            raise HTTPException(status_code=400, detail="DEVICE_ID_REQUIRED")
        store.refresh_oee_runtime_state(module_id, force=True)
        return _build_technician_snapshot(module_id, str(device_id).strip(), technician_name)

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
        _refresh_after_kiosk_write(
            module_id,
            updated_state,
            event_type="started",
            actor_id=actor["operator_code"] or actor["operator_id"],
        )
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
        station_context = _station_context_for_actor(actor)
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
        fault = result.get("fault") if isinstance(result.get("fault"), dict) else {}
        try:
            help_result = oee_state_manager.request_help(
                device_id=actor["device_id"],
                device_name=actor["device_name"],
                bound_station_id=actor["bound_station_id"],
                line_id=station_context["line_id"],
                station_name=station_context["station_name"],
                operator_id=actor["operator_id"],
                operator_code=actor["operator_code"],
                operator_name=actor["operator_name"],
                fault_id=str(fault.get("faultId") or ""),
                fault_code=fault_code,
                reason=fault_text,
                fault_started_at=str(fault.get("startedAt") or ""),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc
        updated_state = help_result.get("state") if isinstance(help_result.get("state"), dict) else None
        _refresh_after_kiosk_write(module_id, updated_state)
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
        request_row = help_result.get("request") if isinstance(help_result.get("request"), dict) else {}
        _record_kiosk_event(
            "help_requested",
            {
                **actor,
                "status": str(request_row.get("status") or "open"),
                "repeat_count": int(request_row.get("repeatCount") or 1),
                "fault_code": str(request_row.get("faultCode") or fault_code),
                "reason": str(request_row.get("reason") or fault_text),
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
            "fault": fault,
            "request": request_row,
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
        station_context = _station_context_for_actor(actor)
        try:
            result = oee_state_manager.request_help(
                device_id=actor["device_id"],
                device_name=actor["device_name"],
                bound_station_id=actor["bound_station_id"],
                line_id=station_context["line_id"],
                station_name=station_context["station_name"],
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

    @app.post("/api/modules/{module_id}/technician/requests/{request_id}/acknowledge")
    async def technician_acknowledge_request(module_id: str, request_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        _ensure_module(module_id)
        actor = _resolve_technician_actor(payload)
        try:
            result = oee_state_manager.acknowledge_help_request(
                request_id,
                technician_name=actor["technician_name"],
                technician_device_id=actor["device_id"],
                technician_device_name=actor["device_name"],
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc
        stamp = utc_now_text()
        _refresh_after_kiosk_write(module_id, result.get("state") if isinstance(result.get("state"), dict) else None)
        request_row = result.get("request") if isinstance(result.get("request"), dict) else {}
        _record_kiosk_event(
            "help_acknowledged",
            {
                "device_id": str(request_row.get("deviceId") or ""),
                "bound_station_id": str(request_row.get("boundStationId") or ""),
                "operator_id": str(request_row.get("operatorId") or ""),
                "fault_code": str(request_row.get("faultCode") or ""),
                "reason": str(request_row.get("reason") or ""),
                "status": str(request_row.get("status") or "acknowledged"),
                "technician_name": actor["technician_name"],
                "response_duration_ms": int(request_row.get("responseDurationMs") or 0),
            },
            received_at=str(request_row.get("acknowledgedAt") or stamp),
        )
        store.append_system_log(
            module_id,
            f"SYSTEM|TECHNICIAN|HELP_ACK|REQUEST={request_id}|TECHNICIAN={actor['technician_name']}",
            topic="local/technician",
            received_at=stamp,
        )
        return {
            "status": "accepted",
            "summary": str(result.get("summary") or ""),
            "request": request_row,
        }

    @app.post("/api/modules/{module_id}/technician/requests/{request_id}/resolve")
    async def technician_resolve_request(module_id: str, request_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        _ensure_module(module_id)
        actor = _resolve_technician_actor(payload)
        try:
            result = oee_state_manager.resolve_help_request(
                request_id,
                technician_name=actor["technician_name"],
                technician_device_id=actor["device_id"],
                technician_device_name=actor["device_name"],
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc
        stamp = utc_now_text()
        _refresh_after_kiosk_write(module_id, result.get("state") if isinstance(result.get("state"), dict) else None)
        request_row = result.get("request") if isinstance(result.get("request"), dict) else {}
        _record_kiosk_event(
            "help_resolved",
            {
                "device_id": str(request_row.get("deviceId") or ""),
                "bound_station_id": str(request_row.get("boundStationId") or ""),
                "operator_id": str(request_row.get("operatorId") or ""),
                "fault_code": str(request_row.get("faultCode") or ""),
                "reason": str(request_row.get("reason") or ""),
                "status": str(request_row.get("status") or "resolved"),
                "technician_name": actor["technician_name"],
                "response_duration_ms": int(request_row.get("responseDurationMs") or 0),
                "repair_duration_ms": int(request_row.get("repairDurationMs") or 0),
                "total_duration_ms": int(request_row.get("totalDurationMs") or 0),
            },
            received_at=str(request_row.get("resolvedAt") or stamp),
        )
        closed_fault = result.get("closed_fault") if isinstance(result.get("closed_fault"), dict) else None
        if closed_fault is not None:
            _record_kiosk_event(
                "kiosk_fault_cleared",
                {
                    "device_id": str(closed_fault.get("deviceId") or ""),
                    "bound_station_id": str(closed_fault.get("boundStationId") or ""),
                    "operator_id": str(closed_fault.get("operatorId") or ""),
                    "fault_code": str(closed_fault.get("reasonCode") or ""),
                    "reason": str(closed_fault.get("reason") or ""),
                    "status": "resolved",
                },
                received_at=str(request_row.get("resolvedAt") or stamp),
            )
        store.append_system_log(
            module_id,
            f"SYSTEM|TECHNICIAN|HELP_RESOLVE|REQUEST={request_id}|TECHNICIAN={actor['technician_name']}",
            topic="local/technician",
            received_at=stamp,
        )
        return {
            "status": "accepted",
            "summary": str(result.get("summary") or ""),
            "request": request_row,
            "fault_closed": closed_fault is not None,
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
        station_code = str(payload.get("station_code") or "").strip().upper()
        mesql_plans: list[Any] = []
        if config.mesql_enabled:
            _require_mesql_local_db()
            mesql_plans = await _sync_mesql_queue(station_code, required=True)
        current_state = oee_state_manager.read_state()
        if str(current_state.get("operationalState") or "") != "shift_active_running":
            raise HTTPException(status_code=400, detail="KIOSK_WORK_ORDER_START_BLOCKED")
        work_orders = current_state.get("workOrders") if isinstance(current_state.get("workOrders"), dict) else {}
        orders_by_id = work_orders.get("ordersById") if isinstance(work_orders.get("ordersById"), dict) else {}
        queued_order_ids = _queued_order_ids(
            orders_by_id,
            work_orders.get("orderSequence") if isinstance(work_orders.get("orderSequence"), list) else [],
            station_code=station_code,
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
        action_now = datetime.now().astimezone()
        remote_result: dict[str, Any] | None = None
        operation_no = 0
        try:
            if config.mesql_enabled:
                plan = _queue_plan_for_order(mesql_plans, order_id, station_code)
                if plan is None:
                    raise HTTPException(
                        status_code=409,
                        detail=_mesql_detail("MESQL_QUEUE_ORDER_NOT_FOUND", "Is emri MESQL istasyon kuyrugunda bulunamadi."),
                    )
                pending_reconciliation = _pending_reconciliation("start", order_id, station_code)
                if pending_reconciliation is not None:
                    return _reconcile_local_transition(
                        "start",
                        action_key=pending_reconciliation[0],
                        order_id=order_id,
                        station_code=station_code,
                        plan=plan,
                        actor_id=actor["operator_code"] or actor["operator_id"],
                    )
                validation = oee_state_manager.validate_start_work_order(
                    order_id,
                    station_code=station_code,
                    transition_reason=transition_reason,
                    started_at=str(payload.get("started_at") or payload.get("startedAt") or ""),
                    now=action_now,
                )
                operation_no = _operation_no(validation["order"], plan)
                operator_id = actor["operator_code"] or actor["operator_id"]
                if not operator_id:
                    raise HTTPException(status_code=400, detail=_mesql_detail("MESQL_OPERATOR_REQUIRED", "MESQL start icin operator gereklidir."))
                remote_result = await _call_mesql_start(
                    order_id,
                    operation_no=operation_no,
                    operator_id=operator_id,
                    station_code=station_code,
                    started_at=validation["started_at_text"],
                )
            result = oee_state_manager.start_work_order(
                order_id,
                station_code=station_code,
                operator_code=actor["operator_code"],
                operator_name=actor["operator_name"],
                transition_reason=transition_reason,
                started_at=str(payload.get("started_at") or payload.get("startedAt") or ""),
                now=action_now,
            )
        except WorkOrderTransitionReasonRequired as exc:
            if remote_result is not None:
                _mark_reconciliation("start", order_id=order_id, operation_no=operation_no, station_code=station_code, remote=remote_result, error=exc)
                raise HTTPException(status_code=500, detail=_mesql_detail("MESQL_RECONCILIATION_REQUIRED", "MESQL start basarili, yerel transition basarisiz.")) from exc
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
        except HTTPException:
            raise
        except ValueError as exc:
            if remote_result is not None:
                _mark_reconciliation("start", order_id=order_id, operation_no=operation_no, station_code=station_code, remote=remote_result, error=exc)
                raise HTTPException(status_code=500, detail=_mesql_detail("MESQL_RECONCILIATION_REQUIRED", "MESQL start basarili, yerel transition basarisiz.")) from exc
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            if remote_result is not None:
                _mark_reconciliation("start", order_id=order_id, operation_no=operation_no, station_code=station_code, remote=remote_result, error=exc)
                raise HTTPException(status_code=500, detail=_mesql_detail("MESQL_RECONCILIATION_REQUIRED", "MESQL start basarili, yerel state yazimi basarisiz.")) from exc
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc
        stamp = utc_now_text()
        updated_state = result.get("state") if isinstance(result.get("state"), dict) else None
        try:
            transition_result = _refresh_after_kiosk_write(
                module_id,
                updated_state,
                event_type="started",
                actor_id=actor["operator_code"] or actor["operator_id"],
            )
        except Exception as exc:
            if config.mesql_enabled:
                _mark_reconciliation("start", order_id=order_id, operation_no=operation_no, station_code=station_code, remote=remote_result or {}, error=exc)
                raise HTTPException(status_code=500, detail=_mesql_detail("MESQL_RECONCILIATION_REQUIRED", "MESQL start basarili, yerel senkronizasyon basarisiz.")) from exc
            raise
        if config.mesql_enabled:
            try:
                _ensure_local_transition_written(transition_result)
            except RuntimeError as exc:
                _mark_reconciliation("start", order_id=order_id, operation_no=operation_no, station_code=station_code, remote=remote_result or {}, error=exc)
                raise HTTPException(status_code=500, detail=_mesql_detail("MESQL_RECONCILIATION_REQUIRED", "MESQL start basarili, yerel DB transition basarisiz.")) from exc
            await _sync_mesql_queue(station_code)
        order = result.get("order") if isinstance(result.get("order"), dict) else {}
        store.append_system_log(
            module_id,
            f"SYSTEM|KIOSK|WORK_ORDER_START|STATION={station_code}|ORDER={order_id}|OPERATOR={actor['operator_code'] or actor['operator_id']}",
            topic="local/kiosk",
            received_at=stamp,
        )
        return {
            "status": "accepted",
            "summary": str(result.get("summary") or ""),
            "order_id": str(order.get("orderId") or order_id),
        }

    @app.post("/api/modules/{module_id}/kiosk/work-orders/accept-active")
    async def kiosk_accept_active_work_order(module_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        _ensure_module(module_id)
        request_payload = payload if isinstance(payload, dict) else {}
        station_code = str(request_payload.get("station_code") or request_payload.get("stationCode") or "").strip().upper()
        order_id = str(request_payload.get("order_id") or request_payload.get("orderId") or "").strip()
        actor = _optional_kiosk_actor(request_payload)
        action_now = datetime.now().astimezone()
        remote_result: dict[str, Any] | None = None
        operation_no = 0
        try:
            if config.mesql_enabled:
                order_id, station_code = _local_work_order_context(order_id, station_code)
                _require_mesql_local_db()
                pending_reconciliation = _pending_reconciliation("complete", order_id, station_code)
                plans = await _sync_mesql_queue(station_code, include_done=pending_reconciliation is not None, required=True)
                plan = _queue_plan_for_order(plans, order_id, station_code)
                if plan is None:
                    raise HTTPException(status_code=409, detail=_mesql_detail("MESQL_QUEUE_ORDER_NOT_FOUND", "Aktif is emri MESQL kuyrugunda bulunamadi."))
                if pending_reconciliation is not None:
                    return _reconcile_local_transition(
                        "complete",
                        action_key=pending_reconciliation[0],
                        order_id=order_id,
                        station_code=station_code,
                        plan=plan,
                        actor_id=actor["operator_code"] or actor["operator_id"] or "KIOSK",
                    )
                validation = oee_state_manager.validate_accept_active_work_order(
                    station_code=station_code,
                    order_id=order_id,
                    now=action_now,
                    require_resolved_rework=True,
                )
                order_id = validation["order_id"]
                station_code = validation["station_code"]
                operation_no = _operation_no(validation["order"], plan)
                snapshot = validation["snapshot"]
                operator_id = actor["operator_code"] or actor["operator_id"] or str(validation["order"].get("startedBy") or "").strip()
                if not operator_id:
                    raise HTTPException(status_code=400, detail=_mesql_detail("MESQL_OPERATOR_REQUIRED", "MESQL complete icin operator gereklidir."))
                remote_result = await _call_mesql_complete(
                    order_id,
                    operation_no=operation_no,
                    operator_id=operator_id,
                    station_code=station_code,
                    good_quantity=float(snapshot.get("goodQty") or 0),
                    scrap_quantity=float(snapshot.get("scrapQty") or 0),
                    uom_code=str(validation["order"].get("unit") or getattr(plan, "uom_code", "") or "ea"),
                    completed_at=validation["accepted_at_text"],
                )
            result = oee_state_manager.accept_active_work_order(station_code=station_code, order_id=order_id, now=action_now)
        except HTTPException:
            raise
        except ValueError as exc:
            if remote_result is not None:
                _mark_reconciliation("complete", order_id=order_id, operation_no=operation_no, station_code=station_code, remote=remote_result, error=exc)
                raise HTTPException(status_code=500, detail=_mesql_detail("MESQL_RECONCILIATION_REQUIRED", "MESQL complete basarili, yerel transition basarisiz.")) from exc
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            if remote_result is not None:
                _mark_reconciliation("complete", order_id=order_id, operation_no=operation_no, station_code=station_code, remote=remote_result, error=exc)
                raise HTTPException(status_code=500, detail=_mesql_detail("MESQL_RECONCILIATION_REQUIRED", "MESQL complete basarili, yerel state yazimi basarisiz.")) from exc
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc
        stamp = utc_now_text()
        updated_state = result.get("state") if isinstance(result.get("state"), dict) else None
        try:
            transition_result = _refresh_after_kiosk_write(
                module_id,
                updated_state,
                event_type="completed",
                actor_id=actor["operator_code"] or actor["operator_id"] or "KIOSK",
            )
        except Exception as exc:
            if config.mesql_enabled:
                _mark_reconciliation("complete", order_id=order_id, operation_no=operation_no, station_code=station_code, remote=remote_result or {}, error=exc)
                raise HTTPException(status_code=500, detail=_mesql_detail("MESQL_RECONCILIATION_REQUIRED", "MESQL complete basarili, yerel senkronizasyon basarisiz.")) from exc
            raise
        if config.mesql_enabled:
            try:
                _ensure_local_transition_written(transition_result)
            except RuntimeError as exc:
                _mark_reconciliation("complete", order_id=order_id, operation_no=operation_no, station_code=station_code, remote=remote_result or {}, error=exc)
                raise HTTPException(status_code=500, detail=_mesql_detail("MESQL_RECONCILIATION_REQUIRED", "MESQL complete basarili, yerel DB transition basarisiz.")) from exc
            await _sync_mesql_queue(station_code, include_done=True)
        order = result.get("order") if isinstance(result.get("order"), dict) else {}
        ferp_export = _ferp_export_acceptance_result(result)
        store.append_system_log(
            module_id,
            f"SYSTEM|KIOSK|WORK_ORDER_ACCEPT|STATION={station_code}|ORDER={str(order.get('orderId') or '')}",
            topic="local/kiosk",
            received_at=stamp,
        )
        return {
            "status": "accepted",
            "summary": str(result.get("summary") or ""),
            "order_id": str(order.get("orderId") or ""),
            "ferp_export": ferp_export,
        }

    @app.post("/api/modules/{module_id}/kiosk/package/start")
    async def kiosk_package_start(module_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        _ensure_module(module_id)
        actor = _optional_kiosk_actor(payload)
        package_order_id = str(payload.get("package_order_id") or payload.get("packageOrderId") or "").strip()
        if not package_order_id:
            raise HTTPException(status_code=400, detail="PACKAGE_ORDER_ID_REQUIRED")
        current_state = oee_state_manager.read_state()
        work_orders = current_state.get("workOrders") if isinstance(current_state.get("workOrders"), dict) else {}
        orders_by_id = work_orders.get("ordersById") if isinstance(work_orders.get("ordersById"), dict) else {}
        package_order = orders_by_id.get(package_order_id) if isinstance(orders_by_id.get(package_order_id), dict) else {}
        availability = package_component_availability(config, current_state, package_order)
        insufficient_detail = insufficient_components_detail(availability, package_order_id)
        if insufficient_detail is not None:
            raise HTTPException(status_code=409, detail=insufficient_detail)
        try:
            result = oee_state_manager.start_package_flow(
                package_order_id,
                item_id=str(payload.get("item_id") or payload.get("itemId") or ""),
                operator_code=actor["operator_code"],
                operator_name=actor["operator_name"],
                device_id=actor["device_id"],
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc
        stamp = utc_now_text()
        updated_state = result.get("state") if isinstance(result.get("state"), dict) else None
        _refresh_after_kiosk_write(
            module_id,
            updated_state,
            event_type="package_started",
            actor_id=actor["operator_code"],
        )
        session = result.get("session") if isinstance(result.get("session"), dict) else {}
        buffer_item = result.get("buffer_item") if isinstance(result.get("buffer_item"), dict) else {}
        reserved_components: list[dict[str, Any]] = []
        try:
            reserved_components = reserve_package_components(
                config,
                package_order_id,
                str(session.get("session_id") or ""),
                availability,
            )
        except Exception as exc:
            logger.error("Package component reservation failed: %s", exc, exc_info=exc)
        upsert_package_session_started(
            config,
            session,
            payload={
                "package_order_id": package_order_id,
                "buffer_item": buffer_item,
                "reserved_components": reserved_components,
            },
        )
        store.append_system_log(
            module_id,
            f"SYSTEM|KIOSK|PACKAGE_START|ORDER={package_order_id}|ITEM={str(buffer_item.get('item_id') or '')}|SESSION={str(session.get('session_id') or '')}",
            topic="local/kiosk",
            received_at=stamp,
        )
        return {
            "status": "accepted",
            "summary": str(result.get("summary") or ""),
            "session_id": str(session.get("session_id") or ""),
            "package_order_id": str(session.get("package_order_id") or package_order_id),
            "buffer_item_id": str(session.get("buffer_item_id") or ""),
            "color": str(session.get("color") or ""),
            "reserved_component_count": len(reserved_components),
        }

    @app.post("/api/modules/{module_id}/kiosk/package/finish")
    async def kiosk_package_finish(module_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        _ensure_module(module_id)
        actor = _optional_kiosk_actor(payload)
        session_id = str(payload.get("session_id") or payload.get("sessionId") or "").strip()
        if not session_id:
            raise HTTPException(status_code=400, detail="PACKAGE_SESSION_ID_REQUIRED")
        try:
            result = oee_state_manager.finish_package_flow(
                session_id,
                operator_code=actor["operator_code"],
                operator_name=actor["operator_name"],
                device_id=actor["device_id"],
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc
        stamp = utc_now_text()
        updated_state = result.get("state") if isinstance(result.get("state"), dict) else None
        _refresh_after_kiosk_write(
            module_id,
            updated_state,
            event_type="package_finished",
            actor_id=actor["operator_code"],
        )
        session = result.get("session") if isinstance(result.get("session"), dict) else {}
        package_item = result.get("package_item") if isinstance(result.get("package_item"), dict) else {}
        updated_work_orders = updated_state.get("workOrders") if isinstance(updated_state, dict) and isinstance(updated_state.get("workOrders"), dict) else {}
        updated_orders_by_id = updated_work_orders.get("ordersById") if isinstance(updated_work_orders.get("ordersById"), dict) else {}
        package_order_id = str(session.get("package_order_id") or "")
        package_order = updated_orders_by_id.get(package_order_id) if isinstance(updated_orders_by_id.get(package_order_id), dict) else {}
        consumed_components: list[dict[str, Any]] = []
        try:
            consumed_components = consume_package_components(
                config,
                package_order=package_order,
                session=session,
                package_item=package_item,
            )
        except Exception as exc:
            logger.error("Package component traceability write failed: %s", exc, exc_info=exc)
        upsert_package_session_finished(
            config,
            session,
            payload={
                "package_item": package_item,
                "consumed_components": consumed_components,
            },
        )
        store.append_system_log(
            module_id,
            f"SYSTEM|KIOSK|PACKAGE_FINISH|ORDER={str(session.get('package_order_id') or '')}|PACKAGE_ITEM={str(package_item.get('item_id') or '')}|SESSION={session_id}",
            topic="local/kiosk",
            received_at=stamp,
        )
        return {
            "status": "accepted",
            "summary": str(result.get("summary") or ""),
            "session_id": str(session.get("session_id") or session_id),
            "package_order_id": str(session.get("package_order_id") or ""),
            "buffer_item_id": str(session.get("buffer_item_id") or ""),
            "package_item_id": str(package_item.get("item_id") or ""),
            "work_order_id": str(package_item.get("work_order_id") or ""),
            "duration_seconds": float(session.get("duration_seconds") or 0),
            "consumed_component_count": len(consumed_components),
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
            sync_work_order_runtime(
                runtime_result.get("state") if isinstance(runtime_result, dict) and isinstance(runtime_result.get("state"), dict) else None,
                event_type="runtime_counts_reset",
            )
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
        sync_work_order_runtime(result.get("state") if isinstance(result.get("state"), dict) else None, event_type="oee_control")
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
        sync_work_order_runtime(result.get("state") if isinstance(result.get("state"), dict) else None, event_type="quality_override")
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
        _reject_mesql_unsupported("work_order_import")

        orders = payload.get("orders")
        replace_existing = bool(payload.get("replace_existing", True))
        try:
            result = oee_state_manager.import_work_orders(orders, replace_existing=replace_existing)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc

        store.refresh_oee_runtime_state(module_id, force=True)
        sync_work_order_runtime(
            result.get("state") if isinstance(result.get("state"), dict) else None,
            event_type="import",
            replace_current=replace_existing,
        )
        summary = str(result.get("summary") or "Is emri listesi guncellendi.")
        store.append_system_log(module_id, f"SYSTEM|WORK_ORDER|IMPORT|COUNT={int(result.get('total_count') or 0)}", topic="local/work-orders")
        return {
            "status": "accepted",
            "summary": summary,
            "queued_count": int(result.get("queued_count") or 0),
            "total_count": int(result.get("total_count") or 0),
            "warnings": list(result.get("warnings") or []),
        }

    @app.post("/api/modules/{module_id}/work-orders/reload")
    async def reload_work_orders(module_id: str) -> dict[str, Any]:
        if module_id != config.module_id:
            raise HTTPException(status_code=404, detail="MODULE_NOT_FOUND")
        _reject_mesql_unsupported("work_order_reload")

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
        sync_work_order_runtime(
            result.get("state") if isinstance(result.get("state"), dict) else None,
            event_type="reload",
            replace_current=True,
        )
        summary = str(result.get("summary") or "Is emri kaynagi yenilendi.")
        store.append_system_log(module_id, f"SYSTEM|WORK_ORDER|RELOAD|FILE={candidates[0].name}", topic="local/work-orders")
        return {
            "status": "accepted",
            "summary": summary,
            "source_file": candidates[0].name,
            "warnings": list(result.get("warnings") or []),
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
        sync_work_order_runtime(result.get("state") if isinstance(result.get("state"), dict) else None, event_type="tolerance_updated")
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
        _reject_mesql_unsupported("work_order_reorder")

        ordered_ids = payload.get("ordered_order_ids") or payload.get("orderedOrderIds") or payload.get("order_ids") or payload.get("orderIds")
        station_code = str(payload.get("station_code") or payload.get("stationCode") or "").strip()
        reason = str(payload.get("reason") or payload.get("transition_reason") or payload.get("transitionReason") or "").strip()
        if not station_code:
            raise HTTPException(status_code=400, detail="WORK_ORDER_STATION_REQUIRED")
        if not isinstance(ordered_ids, list) or not ordered_ids:
            raise HTTPException(status_code=400, detail="WORK_ORDER_REORDER_IDS_REQUIRED")
        if not reason:
            raise HTTPException(status_code=400, detail="WORK_ORDER_REORDER_REASON_REQUIRED")
        try:
            result = oee_state_manager.reorder_work_orders(ordered_ids, station_code=station_code, reason=reason)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc

        store.refresh_oee_runtime_state(module_id, force=True)
        sync_work_order_runtime(result.get("state") if isinstance(result.get("state"), dict) else None, event_type="reordered")
        summary = str(result.get("summary") or "Is emri sirasi guncellendi.")
        store.append_system_log(module_id, f"SYSTEM|WORK_ORDER|REORDER|STATION={station_code or 'GLOBAL'}", topic="local/work-orders")
        return {
            "status": "accepted",
            "summary": summary,
            "station_code": station_code,
        }

    @app.post("/api/modules/{module_id}/work-orders/start")
    async def start_work_order(module_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if module_id != config.module_id:
            raise HTTPException(status_code=404, detail="MODULE_NOT_FOUND")
        order_id = str(payload.get("order_id") or payload.get("orderId") or "").strip()
        station_code = str(payload.get("station_code") or payload.get("stationCode") or "").strip().upper()
        operator_code = str(payload.get("operator_code") or payload.get("operatorCode") or "").strip()
        transition_reason = str(payload.get("transition_reason") or payload.get("transitionReason") or "").strip()
        started_at = str(payload.get("started_at") or payload.get("startedAt") or "").strip()
        action_now = datetime.now().astimezone()
        remote_result: dict[str, Any] | None = None
        operation_no = 0
        try:
            if config.mesql_enabled:
                order_id, station_code = _local_work_order_context(order_id, station_code)
                _require_mesql_local_db()
                plans = await _sync_mesql_queue(station_code, required=True)
                plan = _queue_plan_for_order(plans, order_id, station_code)
                if plan is None:
                    raise HTTPException(status_code=409, detail=_mesql_detail("MESQL_QUEUE_ORDER_NOT_FOUND", "Is emri MESQL istasyon kuyrugunda bulunamadi."))
                pending_reconciliation = _pending_reconciliation("start", order_id, station_code)
                if pending_reconciliation is not None:
                    return _reconcile_local_transition(
                        "start",
                        action_key=pending_reconciliation[0],
                        order_id=order_id,
                        station_code=station_code,
                        plan=plan,
                        actor_id=operator_code,
                    )
                validation = oee_state_manager.validate_start_work_order(
                    order_id,
                    station_code=station_code,
                    transition_reason=transition_reason,
                    started_at=started_at,
                    now=action_now,
                )
                operation_no = _operation_no(validation["order"], plan)
                if not operator_code:
                    raise HTTPException(status_code=400, detail=_mesql_detail("MESQL_OPERATOR_REQUIRED", "MESQL start icin operator gereklidir."))
                remote_result = await _call_mesql_start(
                    order_id,
                    operation_no=operation_no,
                    operator_id=operator_code,
                    station_code=station_code,
                    started_at=validation["started_at_text"],
                )
            result = oee_state_manager.start_work_order(
                order_id,
                station_code=station_code,
                operator_code=operator_code,
                operator_name=str(payload.get("operator_name") or payload.get("operatorName") or ""),
                transition_reason=transition_reason,
                started_at=started_at,
                now=action_now,
            )
        except WorkOrderTransitionReasonRequired as exc:
            if remote_result is not None:
                _mark_reconciliation("start", order_id=order_id, operation_no=operation_no, station_code=station_code, remote=remote_result, error=exc)
                raise HTTPException(status_code=500, detail=_mesql_detail("MESQL_RECONCILIATION_REQUIRED", "MESQL start basarili, yerel transition basarisiz.")) from exc
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
        except HTTPException:
            raise
        except ValueError as exc:
            if remote_result is not None:
                _mark_reconciliation("start", order_id=order_id, operation_no=operation_no, station_code=station_code, remote=remote_result, error=exc)
                raise HTTPException(status_code=500, detail=_mesql_detail("MESQL_RECONCILIATION_REQUIRED", "MESQL start basarili, yerel transition basarisiz.")) from exc
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            if remote_result is not None:
                _mark_reconciliation("start", order_id=order_id, operation_no=operation_no, station_code=station_code, remote=remote_result, error=exc)
                raise HTTPException(status_code=500, detail=_mesql_detail("MESQL_RECONCILIATION_REQUIRED", "MESQL start basarili, yerel state yazimi basarisiz.")) from exc
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc

        try:
            store.refresh_oee_runtime_state(module_id, force=True)
            transition_result = sync_work_order_runtime(
                result.get("state") if isinstance(result.get("state"), dict) else None,
                event_type="started",
                actor_id=operator_code,
            )
        except Exception as exc:
            if config.mesql_enabled:
                _mark_reconciliation("start", order_id=order_id, operation_no=operation_no, station_code=station_code, remote=remote_result or {}, error=exc)
                raise HTTPException(status_code=500, detail=_mesql_detail("MESQL_RECONCILIATION_REQUIRED", "MESQL start basarili, yerel senkronizasyon basarisiz.")) from exc
            raise
        if config.mesql_enabled:
            try:
                _ensure_local_transition_written(transition_result)
            except RuntimeError as exc:
                _mark_reconciliation("start", order_id=order_id, operation_no=operation_no, station_code=station_code, remote=remote_result or {}, error=exc)
                raise HTTPException(status_code=500, detail=_mesql_detail("MESQL_RECONCILIATION_REQUIRED", "MESQL start basarili, yerel DB transition basarisiz.")) from exc
            await _sync_mesql_queue(station_code)
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
    async def accept_active_work_order(module_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if module_id != config.module_id:
            raise HTTPException(status_code=404, detail="MODULE_NOT_FOUND")
        request_payload = payload if isinstance(payload, dict) else {}
        station_code = str(request_payload.get("station_code") or request_payload.get("stationCode") or "").strip().upper()
        order_id = str(request_payload.get("order_id") or request_payload.get("orderId") or "").strip()
        action_now = datetime.now().astimezone()
        remote_result: dict[str, Any] | None = None
        operation_no = 0
        try:
            if config.mesql_enabled:
                order_id, station_code = _local_work_order_context(order_id, station_code)
                _require_mesql_local_db()
                pending_reconciliation = _pending_reconciliation("complete", order_id, station_code)
                plans = await _sync_mesql_queue(station_code, include_done=pending_reconciliation is not None, required=True)
                plan = _queue_plan_for_order(plans, order_id, station_code)
                if plan is None:
                    raise HTTPException(status_code=409, detail=_mesql_detail("MESQL_QUEUE_ORDER_NOT_FOUND", "Aktif is emri MESQL kuyrugunda bulunamadi."))
                if pending_reconciliation is not None:
                    actor_id = str(
                        request_payload.get("operator_id")
                        or request_payload.get("operator_code")
                        or request_payload.get("operatorCode")
                        or ""
                    ).strip()
                    return _reconcile_local_transition(
                        "complete",
                        action_key=pending_reconciliation[0],
                        order_id=order_id,
                        station_code=station_code,
                        plan=plan,
                        actor_id=actor_id,
                    )
                validation = oee_state_manager.validate_accept_active_work_order(
                    station_code=station_code,
                    order_id=order_id,
                    now=action_now,
                    require_resolved_rework=True,
                )
                order_id = validation["order_id"]
                station_code = validation["station_code"]
                operation_no = _operation_no(validation["order"], plan)
                snapshot = validation["snapshot"]
                operator_id = str(
                    request_payload.get("operator_id")
                    or request_payload.get("operator_code")
                    or request_payload.get("operatorCode")
                    or validation["order"].get("startedBy")
                    or ""
                ).strip()
                if not operator_id:
                    raise HTTPException(status_code=400, detail=_mesql_detail("MESQL_OPERATOR_REQUIRED", "MESQL complete icin operator gereklidir."))
                remote_result = await _call_mesql_complete(
                    order_id,
                    operation_no=operation_no,
                    operator_id=operator_id,
                    station_code=station_code,
                    good_quantity=float(snapshot.get("goodQty") or 0),
                    scrap_quantity=float(snapshot.get("scrapQty") or 0),
                    uom_code=str(validation["order"].get("unit") or getattr(plan, "uom_code", "") or "ea"),
                    completed_at=validation["accepted_at_text"],
                )
            result = oee_state_manager.accept_active_work_order(
                station_code=station_code,
                order_id=order_id,
                now=action_now,
            )
        except HTTPException:
            raise
        except ValueError as exc:
            if remote_result is not None:
                _mark_reconciliation("complete", order_id=order_id, operation_no=operation_no, station_code=station_code, remote=remote_result, error=exc)
                raise HTTPException(status_code=500, detail=_mesql_detail("MESQL_RECONCILIATION_REQUIRED", "MESQL complete basarili, yerel transition basarisiz.")) from exc
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            if remote_result is not None:
                _mark_reconciliation("complete", order_id=order_id, operation_no=operation_no, station_code=station_code, remote=remote_result, error=exc)
                raise HTTPException(status_code=500, detail=_mesql_detail("MESQL_RECONCILIATION_REQUIRED", "MESQL complete basarili, yerel state yazimi basarisiz.")) from exc
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc

        try:
            store.refresh_oee_runtime_state(module_id, force=True)
            transition_result = sync_work_order_runtime(result.get("state") if isinstance(result.get("state"), dict) else None, event_type="completed")
        except Exception as exc:
            if config.mesql_enabled:
                _mark_reconciliation("complete", order_id=order_id, operation_no=operation_no, station_code=station_code, remote=remote_result or {}, error=exc)
                raise HTTPException(status_code=500, detail=_mesql_detail("MESQL_RECONCILIATION_REQUIRED", "MESQL complete basarili, yerel senkronizasyon basarisiz.")) from exc
            raise
        if config.mesql_enabled:
            try:
                _ensure_local_transition_written(transition_result)
            except RuntimeError as exc:
                _mark_reconciliation("complete", order_id=order_id, operation_no=operation_no, station_code=station_code, remote=remote_result or {}, error=exc)
                raise HTTPException(status_code=500, detail=_mesql_detail("MESQL_RECONCILIATION_REQUIRED", "MESQL complete basarili, yerel DB transition basarisiz.")) from exc
            await _sync_mesql_queue(station_code, include_done=True)
        order = result.get("order") if isinstance(result.get("order"), dict) else {}
        summary = str(result.get("summary") or "Is emri operator onayi ile kapatildi.")
        ferp_export = _ferp_export_acceptance_result(result)
        store.append_system_log(
            module_id,
            f"SYSTEM|WORK_ORDER|ACCEPT|ORDER={order.get('orderId') or ''}",
            topic="local/work-orders",
        )
        return {
            "status": "accepted",
            "summary": summary,
            "order_id": str(order.get("orderId") or ""),
            "ferp_export": ferp_export,
        }

    @app.post("/api/modules/{module_id}/work-orders/finish")
    async def finish_work_order(module_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if module_id != config.module_id:
            raise HTTPException(status_code=404, detail="MODULE_NOT_FOUND")
        order_id = str(payload.get("order_id") or payload.get("orderId") or "").strip()
        station_code = str(payload.get("station_code") or payload.get("stationCode") or "").strip()
        reason = str(payload.get("reason") or payload.get("transition_reason") or payload.get("transitionReason") or "").strip()
        if not order_id:
            raise HTTPException(status_code=400, detail="WORK_ORDER_ID_REQUIRED")
        if not station_code:
            raise HTTPException(status_code=400, detail="WORK_ORDER_STATION_REQUIRED")
        if not reason:
            raise HTTPException(status_code=400, detail="WORK_ORDER_FINISH_REASON_REQUIRED")
        try:
            result = oee_state_manager.finish_work_order(
                order_id,
                station_code=station_code,
                operator_code=str(payload.get("operator_code") or payload.get("operatorCode") or ""),
                operator_name=str(payload.get("operator_name") or payload.get("operatorName") or ""),
                reason=reason,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc
        store.refresh_oee_runtime_state(module_id, force=True)
        sync_work_order_runtime(
            result.get("state") if isinstance(result.get("state"), dict) else None,
            event_type="finished",
            actor_id=str(payload.get("operator_code") or payload.get("operatorCode") or ""),
        )
        order = result.get("order") if isinstance(result.get("order"), dict) else {}
        store.append_system_log(
            module_id,
            f"SYSTEM|WORK_ORDER|FINISH|STATION={station_code}|ORDER={order.get('orderId') or order_id}",
            topic="local/work-orders",
        )
        return {
            "status": "accepted",
            "summary": str(result.get("summary") or "Is emri bitirildi."),
            "order_id": str(order.get("orderId") or order_id),
            "station_code": station_code,
        }

    @app.post("/api/modules/{module_id}/work-orders/cancel")
    async def cancel_work_order(module_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if module_id != config.module_id:
            raise HTTPException(status_code=404, detail="MODULE_NOT_FOUND")
        _reject_mesql_unsupported("work_order_cancel")
        order_id = str(payload.get("order_id") or payload.get("orderId") or "").strip()
        station_code = str(payload.get("station_code") or payload.get("stationCode") or "").strip()
        reason = str(payload.get("reason") or payload.get("transition_reason") or payload.get("transitionReason") or "").strip()
        if not order_id:
            raise HTTPException(status_code=400, detail="WORK_ORDER_ID_REQUIRED")
        if not station_code:
            raise HTTPException(status_code=400, detail="WORK_ORDER_STATION_REQUIRED")
        if not reason:
            raise HTTPException(status_code=400, detail="WORK_ORDER_CANCEL_REASON_REQUIRED")
        try:
            result = oee_state_manager.cancel_work_order(
                order_id,
                station_code=station_code,
                operator_code=str(payload.get("operator_id") or payload.get("operator_code") or payload.get("operatorCode") or ""),
                operator_name=str(payload.get("operator_name") or payload.get("operatorName") or ""),
                device_id=str(payload.get("device_id") or payload.get("deviceId") or ""),
                reason=reason,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc
        released_components: list[dict[str, Any]] = []
        for session_id in result.get("released_package_session_ids") or []:
            try:
                released_components.extend(
                    release_reserved_package_components(
                        config,
                        package_order_id=order_id,
                        package_session_id=str(session_id or ""),
                    )
                )
            except Exception as exc:
                logger.error("Package WIP release failed after cancel: %s", exc, exc_info=exc)
            result_state = result.get("state") if isinstance(result.get("state"), dict) else {}
            work_orders = result_state.get("workOrders") if isinstance(result_state.get("workOrders"), dict) else {}
            sessions = work_orders.get("packagingSessions") if isinstance(work_orders.get("packagingSessions"), dict) else {}
            session = sessions.get(str(session_id or "")) if isinstance(sessions.get(str(session_id or "")), dict) else {}
            upsert_package_session_cancelled(
                config,
                session,
                payload={
                    "package_order_id": order_id,
                    "reason": reason,
                    "released_components": released_components,
                },
            )
        store.refresh_oee_runtime_state(module_id, force=True)
        sync_work_order_runtime(
            result.get("state") if isinstance(result.get("state"), dict) else None,
            event_type="cancelled",
            actor_id=str(payload.get("operator_id") or payload.get("operator_code") or payload.get("operatorCode") or ""),
        )
        order = result.get("order") if isinstance(result.get("order"), dict) else {}
        store.append_system_log(
            module_id,
            f"SYSTEM|WORK_ORDER|CANCEL|STATION={station_code}|ORDER={order.get('orderId') or order_id}|REASON={reason}",
            topic="local/work-orders",
        )
        return {
            "status": "accepted",
            "summary": str(result.get("summary") or "Is emri iptal edildi."),
            "order_id": str(order.get("orderId") or order_id),
            "station_code": station_code,
            "previous_status": str(result.get("previous_status") or ""),
            "released_package_session_count": len(result.get("released_package_session_ids") or []),
            "released_component_count": len(released_components),
        }

    @app.post("/api/modules/{module_id}/work-orders/rollback-active")
    async def rollback_active_work_order(module_id: str) -> dict[str, Any]:
        if module_id != config.module_id:
            raise HTTPException(status_code=404, detail="MODULE_NOT_FOUND")
        _reject_mesql_unsupported("work_order_rollback")

        try:
            result = oee_state_manager.rollback_active_work_order()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc

        store.refresh_oee_runtime_state(module_id, force=True)
        sync_work_order_runtime(result.get("state") if isinstance(result.get("state"), dict) else None, event_type="rolled_back")
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
    async def reset_work_orders(module_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if module_id != config.module_id:
            raise HTTPException(status_code=404, detail="MODULE_NOT_FOUND")
        _reject_mesql_unsupported("work_order_reset")
        request_payload = payload if isinstance(payload, dict) else {}
        reset_wip = bool(request_payload.get("reset_wip", request_payload.get("resetWip", True)))

        planning_snapshot: dict[str, Any] = {}
        try:
            planning_snapshot = load_work_order_planning_snapshot(config)
        except Exception as exc:
            logger.warning("Work order DB planning snapshot failed before reset: %s", exc)
        try:
            result = oee_state_manager.reset_work_orders()
        except OSError as exc:
            raise HTTPException(status_code=500, detail="OEE_STATE_WRITE_FAILED") from exc

        store.refresh_oee_runtime_state(module_id, force=True)
        db_reset_result = reset_work_order_operational_state(config, planning_snapshot=planning_snapshot)
        if db_reset_result.status == "error":
            logger.warning("Work order DB operational reset failed: %s", db_reset_result.message)
        wip_reset_count = 0
        if reset_wip:
            try:
                wip_reset_count = reset_demo_package_wip(config, reason="work_order_reset")
            except Exception as exc:
                logger.warning("Demo package WIP reset failed: %s", exc, exc_info=exc)
        sync_work_order_runtime(
            result.get("state") if isinstance(result.get("state"), dict) else None,
            event_type="reset",
            replace_current=False,
            mirror_current=False,
        )
        summary = str(result.get("summary") or "Is emirleri sifirlandi.")
        store.append_system_log(
            module_id,
            f"SYSTEM|WORK_ORDER|RESET|CLEARED={int(result.get('cleared_item_count') or 0)}|PRESERVED={int(result.get('preserved_order_count') or 0)}|DB_ROWS={int(db_reset_result.row_count or 0)}|WIP_RESET={wip_reset_count}",
            topic="local/work-orders",
        )
        return {
            "status": "accepted",
            "summary": summary,
            "cleared_item_count": int(result.get("cleared_item_count") or 0),
            "preserved_order_count": int(result.get("preserved_order_count") or 0),
            "db_reset_status": db_reset_result.status,
            "db_reset_row_count": int(db_reset_result.row_count or 0),
            "wip_reset_count": int(wip_reset_count),
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
        sync_work_order_runtime(result.get("state") if isinstance(result.get("state"), dict) else None, event_type="inventory_updated")
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
    async def kiosk_stream(websocket: WebSocket, module_id: str, device_id: str, station_code: str = "") -> None:
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
                    "data": _build_kiosk_snapshot(module_id, str(device_id).strip(), station_code=station_code),
                }
            )
            while True:
                await queue.get()
                await websocket.send_json(
                    {
                        "type": "kiosk_snapshot",
                        "module_id": module_id,
                        "device_id": str(device_id).strip(),
                        "data": _build_kiosk_snapshot(module_id, str(device_id).strip(), station_code=station_code),
                    }
                )
        except WebSocketDisconnect:
            pass
        except OSError as exc:
            if not _is_benign_socket_disconnect_error(exc):
                raise
        finally:
            await hub.unregister(module_id, queue)

    @app.websocket("/ws/modules/{module_id}/technician/{device_id}")
    async def technician_stream(websocket: WebSocket, module_id: str, device_id: str) -> None:
        if module_id != config.module_id or not str(device_id or "").strip():
            await websocket.close(code=4404)
            return
        technician_name = str(websocket.query_params.get("technician_name") or "").strip()
        try:
            oee_state_manager.register_kiosk_device(
                device_id=str(device_id).strip(),
                device_name=str(device_id).strip(),
                device_role="technician_kiosk",
            )
            store.refresh_oee_runtime_state(module_id, force=True)
        except OSError:
            pass
        await websocket.accept()
        queue = await hub.register(module_id)
        try:
            await websocket.send_json(
                {
                    "type": "technician_snapshot",
                    "module_id": module_id,
                    "device_id": str(device_id).strip(),
                    "data": _build_technician_snapshot(module_id, str(device_id).strip(), technician_name),
                }
            )
            while True:
                await queue.get()
                await websocket.send_json(
                    {
                        "type": "technician_snapshot",
                        "module_id": module_id,
                        "device_id": str(device_id).strip(),
                        "data": _build_technician_snapshot(module_id, str(device_id).strip(), technician_name),
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
                    "data": _build_dashboard_snapshot(module_id),
                }
            )
            while True:
                message = await queue.get()
                if isinstance(message, dict) and message.get("type") == "dashboard_snapshot":
                    message = {**message, "data": _build_dashboard_snapshot(module_id)}
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

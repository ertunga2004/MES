from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ..config import AppConfig
from .connection import database_connection


JsonObject = dict[str, Any]
logger = logging.getLogger(__name__)
DEMO_COMPONENT_STOCK_CODES = ("RED_BOX", "BLUE_BOX", "YELLOW_BOX")
DEMO_PACKAGE_BOM_LINES: dict[str, list[JsonObject]] = {
    "PKG_BLUE_3": [{"component_stock_code": "BLUE_BOX", "required_qty": 3, "color_code": "blue"}],
    "PKT-BLUE": [{"component_stock_code": "BLUE_BOX", "required_qty": 3, "color_code": "blue"}],
    "PKG_RED_3": [{"component_stock_code": "RED_BOX", "required_qty": 2, "color_code": "red"}],
    "PKT-RED": [{"component_stock_code": "RED_BOX", "required_qty": 2, "color_code": "red"}],
    "PKG_YELLOW_3": [{"component_stock_code": "YELLOW_BOX", "required_qty": 1, "color_code": "yellow"}],
    "PKT-YELLOW": [{"component_stock_code": "YELLOW_BOX", "required_qty": 1, "color_code": "yellow"}],
}


@dataclass(frozen=True, slots=True)
class PackageComponentRequirement:
    component_stock_code: str
    required_qty: int
    required_total: int
    available_qty: int
    missing_qty: int
    color_code: str

    def as_dict(self) -> JsonObject:
        return {
            "component_stock_code": self.component_stock_code,
            "required_qty": self.required_qty,
            "required_total": self.required_total,
            "available_qty": self.available_qty,
            "missing_qty": self.missing_qty,
            "color_code": self.color_code,
        }


def _jsonb(value: Any) -> Any:
    try:
        from psycopg.types.json import Jsonb
    except ModuleNotFoundError:
        return value
    return Jsonb(value)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _upper(value: Any) -> str:
    return _text(value).upper()


def _positive_int(value: Any, default: int = 0) -> int:
    try:
        parsed = int(float(str(value or "").replace(",", ".").strip()))
    except ValueError:
        return max(0, default)
    return max(0, parsed)


def _first_text(row: JsonObject, *names: str) -> str:
    for name in names:
        value = _text(row.get(name))
        if value:
            return value
    return ""


def package_stock_code_for_order(order: JsonObject | None) -> str:
    if not isinstance(order, dict):
        return ""
    raw = _upper(_first_text(order, "package_stock_code", "packageSku", "package_sku", "stock_code", "stockCode", "productCode"))
    name = _upper(_first_text(order, "stock_name", "stockName", "name"))
    marker = f"{raw} {name}"
    if raw in {"PKT-BLUE", "BLUE-PACKAGE"} or "BLUE" in marker or "MAVI" in marker or "MAVİ" in marker:
        return "PKG_BLUE_3" if raw != "PKT-BLUE" else "PKT-BLUE"
    if raw in {"PKT-RED", "RED-PACKAGE"} or "RED" in marker or "KIRMIZI" in marker:
        return "PKG_RED_3" if raw != "PKT-RED" else "PKT-RED"
    if raw in {"PKT-YELLOW", "YELLOW-PACKAGE"} or "YELLOW" in marker or "SARI" in marker:
        return "PKG_YELLOW_3" if raw != "PKT-YELLOW" else "PKT-YELLOW"
    return raw


def component_stock_code_for_item(item: JsonObject | None) -> str:
    if not isinstance(item, dict):
        return ""
    raw = _upper(_first_text(item, "component_stock_code", "stock_code", "stockCode", "product_code", "productCode"))
    color = _upper(_first_text(item, "color", "display_color", "displayColor", "product_color", "productColor"))
    marker = f"{raw} {color}"
    if raw in {"BLUE_BOX", "BOX-BLUE"} or "BLUE" in marker or "MAVI" in marker or "MAVİ" in marker:
        return "BLUE_BOX"
    if raw in {"RED_BOX", "BOX-RED"} or "RED" in marker or "KIRMIZI" in marker:
        return "RED_BOX"
    if raw in {"YELLOW_BOX", "BOX-YELLOW", "BOX-YEL"} or "YELLOW" in marker or "SARI" in marker:
        return "YELLOW_BOX"
    return raw


def color_for_component(component_stock_code: str) -> str:
    code = _upper(component_stock_code)
    if "BLUE" in code:
        return "blue"
    if "RED" in code:
        return "red"
    if "YELLOW" in code:
        return "yellow"
    return ""


def _runtime_available_component_rows(state: JsonObject) -> list[JsonObject]:
    work_orders = state.get("workOrders") if isinstance(state.get("workOrders"), dict) else {}
    buffer = work_orders.get("packagingBuffer") if isinstance(work_orders.get("packagingBuffer"), dict) else {}
    items_by_id = buffer.get("itemsById") if isinstance(buffer.get("itemsById"), dict) else {}
    available_ids = {str(value) for value in buffer.get("availableItemIds", [])} if isinstance(buffer.get("availableItemIds"), list) else set()
    rows: list[JsonObject] = []
    for key, item in items_by_id.items():
        if not isinstance(item, dict):
            continue
        item_id = _text(item.get("item_id") or item.get("itemId") or key)
        if available_ids and item_id not in available_ids:
            continue
        if _text(item.get("status")).lower() and _text(item.get("status")).lower() != "available":
            continue
        classification = _upper(item.get("classification") or "GOOD")
        if classification != "GOOD":
            continue
        component_stock_code = component_stock_code_for_item(item)
        if not component_stock_code:
            continue
        source_work_order_id = _first_text(item, "work_order_id", "workOrderId", "upstream_order_id", "upstreamOrderId")
        if not source_work_order_id or not item_id:
            continue
        external_ref = _text(item.get("external_ref") or item.get("externalRef"))
        if not external_ref:
            external_ref = f"runtime_buffer:{item_id}"
        rows.append(
            {
                "component_stock_code": component_stock_code,
                "color_code": _text(item.get("color") or item.get("display_color") or color_for_component(component_stock_code)).lower(),
                "source_work_order_id": source_work_order_id,
                "source_item_id": item_id,
                "source_external_ref": external_ref,
                "quality_status": classification,
                "completed_at": _text(item.get("completed_at") or item.get("completedAt")) or None,
                "payload": dict(item),
            }
        )
    return rows


def sync_runtime_package_wip(config: AppConfig, state: JsonObject) -> int:
    rows = _runtime_available_component_rows(state)
    if not rows:
        return 0
    with database_connection(config) as connection:
        if connection is None:
            return 0
        with connection.cursor() as cursor:
            for row in rows:
                cursor.execute(
                    """
                    INSERT INTO mes.package_component_wip (
                        component_stock_code,
                        color_code,
                        source_work_order_id,
                        source_item_id,
                        source_external_ref,
                        quality_status,
                        status,
                        completed_at,
                        source_system,
                        payload,
                        metadata,
                        updated_at
                    ) VALUES (
                        %(component_stock_code)s,
                        %(color_code)s,
                        %(source_work_order_id)s,
                        %(source_item_id)s,
                        %(source_external_ref)s,
                        %(quality_status)s,
                        'available',
                        %(completed_at)s,
                        'mes_web_runtime',
                        %(payload)s,
                        %(metadata)s,
                        now()
                    )
                    ON CONFLICT (source_external_ref) WHERE source_external_ref IS NOT NULL AND btrim(source_external_ref) <> ''
                    DO UPDATE SET
                        component_stock_code = EXCLUDED.component_stock_code,
                        color_code = EXCLUDED.color_code,
                        source_work_order_id = EXCLUDED.source_work_order_id,
                        source_item_id = EXCLUDED.source_item_id,
                        quality_status = EXCLUDED.quality_status,
                        completed_at = EXCLUDED.completed_at,
                        payload = EXCLUDED.payload,
                        metadata = mes.package_component_wip.metadata || EXCLUDED.metadata,
                        updated_at = now()
                    WHERE mes.package_component_wip.status = 'available'
                    """,
                    {
                        **row,
                        "payload": _jsonb(row["payload"]),
                        "metadata": _jsonb({"sync": "runtime_packaging_buffer"}),
                    },
                )
    return len(rows)


def _read_bom_lines(config: AppConfig, package_stock_code: str) -> list[JsonObject]:
    if not package_stock_code:
        return []
    demo_lines = DEMO_PACKAGE_BOM_LINES.get(_upper(package_stock_code))
    if demo_lines is not None:
        return [dict(row) for row in demo_lines]
    with database_connection(config) as connection:
        if connection is None:
            return []
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT component_stock_code, required_qty, COALESCE(color_code, '') AS color_code
                FROM mes.package_bom_lines
                WHERE active = true
                  AND package_stock_code = %s
                  AND valid_from <= now()
                  AND (valid_to IS NULL OR valid_to > now())
                ORDER BY bom_line_id
                """,
                (package_stock_code,),
            )
            return [
                {
                    "component_stock_code": _text(row[0]),
                    "required_qty": int(row[1] or 0),
                    "color_code": _text(row[2]),
                }
                for row in cursor.fetchall()
            ]


def _available_counts(config: AppConfig, component_codes: list[str]) -> dict[str, int]:
    if not component_codes:
        return {}
    with database_connection(config) as connection:
        if connection is None:
            return {}
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT component_stock_code, COUNT(*)::int
                FROM mes.package_component_wip
                WHERE status = 'available'
                  AND quality_status = 'GOOD'
                  AND component_stock_code = ANY(%s)
                  AND COALESCE(btrim(source_work_order_id), '') <> ''
                  AND COALESCE(btrim(source_item_id), '') <> ''
                  AND COALESCE(btrim(reserved_by_order_id), '') = ''
                  AND COALESCE(btrim(reserved_by_session_id), '') = ''
                  AND COALESCE(btrim(consumed_by_package_id), '') = ''
                  AND consumed_at IS NULL
                GROUP BY component_stock_code
                """,
                (component_codes,),
            )
            return {_text(row[0]): int(row[1] or 0) for row in cursor.fetchall()}


def package_component_availability(config: AppConfig, state: JsonObject, order: JsonObject | None) -> JsonObject:
    package_stock_code = package_stock_code_for_order(order)
    if not config.db_enabled or not package_stock_code:
        return {"enabled": False, "package_stock_code": package_stock_code, "can_start": True, "components": []}
    try:
        sync_runtime_package_wip(config, state)
        bom_lines = _read_bom_lines(config, package_stock_code)
        if not bom_lines:
            return {"enabled": True, "bom_configured": False, "package_stock_code": package_stock_code, "can_start": True, "components": []}
        counts = _available_counts(config, [row["component_stock_code"] for row in bom_lines])
    except Exception as exc:
        logger.warning("Package BOM availability skipped: %s", exc)
        return {
            "enabled": True,
            "error": type(exc).__name__,
            "package_stock_code": package_stock_code,
            "can_start": True,
            "components": [],
        }
    order_qty = max(1, _positive_int((order or {}).get("qty") or (order or {}).get("quantity") or (order or {}).get("target_quantity"), 1))
    components = []
    for row in bom_lines:
        required_qty = _positive_int(row.get("required_qty"))
        required_total = required_qty * order_qty
        available_qty = int(counts.get(row["component_stock_code"], 0))
        components.append(
            PackageComponentRequirement(
                component_stock_code=row["component_stock_code"],
                required_qty=required_qty,
                required_total=required_total,
                available_qty=available_qty,
                missing_qty=max(required_total - available_qty, 0),
                color_code=_text(row.get("color_code")) or color_for_component(row["component_stock_code"]),
            ).as_dict()
        )
    return {
        "enabled": True,
        "bom_configured": True,
        "package_stock_code": package_stock_code,
        "can_start": all(int(row["missing_qty"]) <= 0 for row in components),
        "components": components,
    }


def insufficient_components_detail(availability: JsonObject, package_order_id: str) -> JsonObject | None:
    components = [row for row in availability.get("components", []) if isinstance(row, dict) and int(row.get("missing_qty") or 0) > 0]
    if not components:
        return None
    return {
        "code": "PACKAGE_COMPONENTS_NOT_AVAILABLE",
        "package_order_id": package_order_id,
        "package_stock_code": _text(availability.get("package_stock_code")),
        "components": components,
    }


def reserve_package_components(config: AppConfig, package_order_id: str, package_session_id: str, availability: JsonObject) -> list[JsonObject]:
    if not config.db_enabled or not availability.get("bom_configured"):
        return []
    reserved: list[JsonObject] = []
    with database_connection(config) as connection:
        if connection is None:
            return []
        with connection.cursor() as cursor:
            for component in availability.get("components", []):
                if not isinstance(component, dict):
                    continue
                component_stock_code = _text(component.get("component_stock_code"))
                required_qty = int(component.get("required_total") or component.get("required_qty") or 0)
                if not component_stock_code or required_qty <= 0:
                    continue
                cursor.execute(
                    """
                    WITH picked AS (
                        SELECT wip_item_pk
                        FROM mes.package_component_wip
                        WHERE component_stock_code = %(component_stock_code)s
                          AND status = 'available'
                          AND quality_status = 'GOOD'
                          AND COALESCE(btrim(source_work_order_id), '') <> ''
                          AND COALESCE(btrim(source_item_id), '') <> ''
                          AND COALESCE(btrim(reserved_by_order_id), '') = ''
                          AND COALESCE(btrim(reserved_by_session_id), '') = ''
                          AND COALESCE(btrim(consumed_by_package_id), '') = ''
                          AND consumed_at IS NULL
                        ORDER BY completed_at NULLS LAST, wip_item_pk
                        LIMIT %(required_qty)s
                        FOR UPDATE SKIP LOCKED
                    )
                    UPDATE mes.package_component_wip wip
                    SET status = 'reserved',
                        reserved_by_order_id = %(package_order_id)s,
                        reserved_by_session_id = %(package_session_id)s,
                        reserved_at = now(),
                        updated_at = now()
                    FROM picked
                    WHERE wip.wip_item_pk = picked.wip_item_pk
                    RETURNING wip.wip_item_pk, wip.component_stock_code, wip.source_item_id
                    """,
                    {
                        "component_stock_code": component_stock_code,
                        "required_qty": required_qty,
                        "package_order_id": package_order_id,
                        "package_session_id": package_session_id,
                    },
                )
                rows = cursor.fetchall()
                if len(rows) < required_qty:
                    raise RuntimeError("PACKAGE_COMPONENT_RESERVATION_RACE")
                reserved.extend(
                    {
                        "wip_item_pk": int(row[0]),
                        "component_stock_code": _text(row[1]),
                        "source_item_id": _text(row[2]),
                    }
                    for row in rows
                )
    return reserved


def reset_demo_package_wip(
    config: AppConfig,
    *,
    stock_codes: list[str] | tuple[str, ...] | None = None,
    source_work_order_ids: list[str] | tuple[str, ...] | None = None,
    reason: str = "work_order_reset",
) -> int:
    if not config.db_enabled:
        return 0
    target_stock_codes = [_upper(value) for value in (stock_codes or DEMO_COMPONENT_STOCK_CODES) if _upper(value)]
    target_order_ids = [_text(value) for value in (source_work_order_ids or []) if _text(value)]
    if not target_stock_codes:
        return 0
    with database_connection(config) as connection:
        if connection is None:
            return 0
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE mes.package_component_wip
                SET status = 'scrapped',
                    reserved_by_order_id = NULL,
                    reserved_by_session_id = NULL,
                    consumed_by_package_id = NULL,
                    reserved_at = NULL,
                    updated_at = now(),
                    metadata = metadata || %(metadata)s
                WHERE component_stock_code = ANY(%(stock_codes)s)
                  AND status IN ('available', 'reserved')
                  AND (
                    %(has_source_filter)s = false
                    OR source_work_order_id = ANY(%(source_work_order_ids)s)
                  )
                """,
                {
                    "stock_codes": target_stock_codes,
                    "source_work_order_ids": target_order_ids,
                    "has_source_filter": bool(target_order_ids),
                    "metadata": _jsonb({"last_reset_reason": _text(reason) or "work_order_reset"}),
                },
            )
            row_count = int(getattr(cursor, "rowcount", 0) or 0)
        commit = getattr(connection, "commit", None)
        if callable(commit):
            commit()
    return row_count


def release_reserved_package_components(config: AppConfig, *, package_order_id: str, package_session_id: str) -> list[JsonObject]:
    if not config.db_enabled:
        return []
    package_order_id = _text(package_order_id)
    package_session_id = _text(package_session_id)
    if not package_order_id or not package_session_id:
        return []
    with database_connection(config) as connection:
        if connection is None:
            return []
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE mes.package_component_wip
                SET status = 'available',
                    reserved_by_order_id = NULL,
                    reserved_by_session_id = NULL,
                    reserved_at = NULL,
                    updated_at = now(),
                    metadata = metadata || %(metadata)s
                WHERE reserved_by_order_id = %(package_order_id)s
                  AND reserved_by_session_id = %(package_session_id)s
                  AND status = 'reserved'
                RETURNING wip_item_pk, component_stock_code, source_item_id
                """,
                {
                    "package_order_id": package_order_id,
                    "package_session_id": package_session_id,
                    "metadata": _jsonb({"last_release_source": "work_order_cancel"}),
                },
            )
            return [
                {
                    "wip_item_pk": int(row[0]),
                    "component_stock_code": _text(row[1]),
                    "source_item_id": _text(row[2]),
                }
                for row in cursor.fetchall()
            ]


def consume_package_components(
    config: AppConfig,
    *,
    package_order: JsonObject,
    session: JsonObject,
    package_item: JsonObject,
) -> list[JsonObject]:
    if not config.db_enabled:
        return []
    package_order_id = _text(session.get("package_order_id") or package_order.get("order_id") or package_order.get("orderId"))
    package_session_id = _text(session.get("session_id"))
    package_item_id = _text(package_item.get("item_id") or package_item.get("itemId"))
    package_stock_code = package_stock_code_for_order(package_order)
    if not package_order_id or not package_session_id:
        return []
    with database_connection(config) as connection:
        if connection is None:
            return []
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE mes.package_component_wip
                SET status = 'consumed',
                    consumed_by_package_id = %(package_item_id)s,
                    consumed_at = now(),
                    updated_at = now()
                WHERE reserved_by_session_id = %(package_session_id)s
                  AND status = 'reserved'
                RETURNING wip_item_pk, component_stock_code, source_item_id
                """,
                {"package_session_id": package_session_id, "package_item_id": package_item_id},
            )
            consumed = [
                {
                    "wip_item_pk": int(row[0]),
                    "component_stock_code": _text(row[1]),
                    "source_item_id": _text(row[2]),
                }
                for row in cursor.fetchall()
            ]
            grouped: dict[str, list[JsonObject]] = {}
            for row in consumed:
                grouped.setdefault(str(row["component_stock_code"]), []).append(row)
            for component_stock_code, rows in grouped.items():
                external_ref = f"{package_order_id}:{package_session_id}:{component_stock_code}"
                cursor.execute(
                    """
                    INSERT INTO mes.package_traceability (
                        package_order_id,
                        package_item_id,
                        package_session_id,
                        package_stock_code,
                        component_stock_code,
                        component_qty,
                        component_wip_ids,
                        source_item_ids,
                        external_ref,
                        payload,
                        metadata
                    ) VALUES (
                        %(package_order_id)s,
                        %(package_item_id)s,
                        %(package_session_id)s,
                        %(package_stock_code)s,
                        %(component_stock_code)s,
                        %(component_qty)s,
                        %(component_wip_ids)s,
                        %(source_item_ids)s,
                        %(external_ref)s,
                        %(payload)s,
                        %(metadata)s
                    )
                    ON CONFLICT (external_ref) WHERE external_ref IS NOT NULL AND btrim(external_ref) <> ''
                    DO UPDATE SET
                        package_item_id = EXCLUDED.package_item_id,
                        component_qty = EXCLUDED.component_qty,
                        component_wip_ids = EXCLUDED.component_wip_ids,
                        source_item_ids = EXCLUDED.source_item_ids,
                        payload = EXCLUDED.payload,
                        metadata = mes.package_traceability.metadata || EXCLUDED.metadata
                    """,
                    {
                        "package_order_id": package_order_id,
                        "package_item_id": package_item_id,
                        "package_session_id": package_session_id,
                        "package_stock_code": package_stock_code,
                        "component_stock_code": component_stock_code,
                        "component_qty": len(rows),
                        "component_wip_ids": _jsonb([row["wip_item_pk"] for row in rows]),
                        "source_item_ids": _jsonb([row["source_item_id"] for row in rows if row.get("source_item_id")]),
                        "external_ref": external_ref,
                        "payload": _jsonb({"session": dict(session), "package_item": dict(package_item)}),
                        "metadata": _jsonb({"source": "phase2a_package_finish"}),
                    },
                )
            return consumed

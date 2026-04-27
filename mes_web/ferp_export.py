from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .ferp_labels import validate_label_payload


EXPORT_SCHEMA = "ferp_mes_export.v1"

WORK_ORDER_LABEL_MAPPING = {
    "order_id": "lblMMFB0_NUMBER",
    "quantity": "lblMMFB0_QTY",
    "target_qty": "lblMMFB0_QTY",
    "date": "lblMMFB0_DATE",
    "stock_code": "lblMTM00_CODE",
    "stock_name": "lblMTM00_NAME",
    "unit": "lblMUNT0_CODE",
    "work_center": "lblMFW00_CODE",
    "work_station": "lblMFW01_CODE",
    "operation": "lblMFWO0_CODE",
    "cycle_time_sec": "lblMMFB4_TIME",
}

MATERIAL_MOVEMENT_LABEL_MAPPING = {
    "date": "lblMMV00_DATE",
    "reference_number": "lblMMV00_REF_NUMBER",
    "description": "lblMMV00_DESC",
    "material_code": "lblMTM00_CODE",
    "raw_material_code": "lblMTM00_CODE",
    "semi_finished_code": "lblMTM00_CODE",
    "finished_code": "lblMTM00_CODE",
    "material_name": "lblMTM00_NAME",
    "unit": "lblMUNT0_CODE",
    "warehouse": "lblMWR00_CODE",
    "location": "lblMWR01_CODE",
    "warehouse_out": "lblMWR00_CODE_O",
    "location_out": "lblMWR01_CODE_O",
    "warehouse_in": "lblMWR00_CODE_I",
    "location_in": "lblMWR01_CODE_I",
}

STATION_FLOW_TEMPLATE = [
    {
        "station_id": "SENSOR-01",
        "input_stage": "RAW",
        "output_stage": "SEMI_FINISHED",
        "event_fields": ("sensor_at", "detected_at", "received_at", "created_at", "updated_at"),
    },
    {
        "station_id": "VISION-01",
        "input_stage": "SEMI_FINISHED",
        "output_stage": "SEMI_FINISHED",
        "event_fields": ("vision_observed_at", "vision_received_at", "vision_decision_at", "vision_at"),
    },
    {
        "station_id": "ROBOT-01",
        "input_stage": "SEMI_FINISHED",
        "output_stage": "FINISHED",
        "event_fields": ("completed_at", "released_at"),
    },
]


def sanitize_filename_token(value: Any) -> str:
    token = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    token = token.strip("._-")
    return token or "UNKNOWN"


def safe_export_timestamp(value: Any = None) -> str:
    stamp: datetime
    if isinstance(value, datetime):
        stamp = value
    elif value:
        parsed = str(value).strip().replace("Z", "+00:00")
        try:
            stamp = datetime.fromisoformat(parsed)
        except ValueError:
            return sanitize_filename_token(value)
    else:
        stamp = datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    stamp = stamp.astimezone(timezone.utc)
    return stamp.strftime("%Y%m%dT%H%M%S%fZ")


def _iso_text(value: Any = None) -> str:
    if isinstance(value, datetime):
        stamp = value
    elif value:
        return str(value)
    else:
        stamp = datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.isoformat()


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _number(value: Any) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        return float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def _quantity(value: Any) -> int:
    return max(0, round(_number(value)))


def _classification(value: Any) -> str:
    normalized = str(value or "").strip().upper()
    if normalized in {"GOOD", "REWORK", "SCRAP"}:
        return normalized
    return "GOOD"


def _iter_items(items: Any) -> list[dict[str, Any]]:
    if isinstance(items, dict):
        source = items.values()
    elif isinstance(items, list):
        source = items
    else:
        source = []
    return [dict(item) for item in source if isinstance(item, dict)]


def _linked_items(items: Any, order_id: str) -> list[dict[str, Any]]:
    linked: list[dict[str, Any]] = []
    for item in _iter_items(items):
        if _text(item.get("work_order_id")) == order_id:
            linked.append(item)
    return linked


def _first_text(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = _text(row.get(key))
        if value:
            return value
    return ""


def _item_id(item: dict[str, Any], fallback_index: int) -> str:
    return _first_text(item, "item_id", "id", "tag_id") or f"item-{fallback_index}"


def _material_code(order: dict[str, Any], item: dict[str, Any] | None = None, *, stage: str = "") -> str:
    source = item if isinstance(item, dict) else {}
    candidate = _first_text(source, "stock_code", "product_code", "final_color", "color")
    if candidate:
        return candidate
    order_code = _first_text(order, "stockCode", "productCode", "stock_code", "product_code")
    suffix = stage.upper().replace(" ", "_") if stage else "MAT"
    return order_code or suffix


def _material_name(order: dict[str, Any], item: dict[str, Any] | None = None, *, stage: str = "") -> str:
    source = item if isinstance(item, dict) else {}
    return (
        _first_text(source, "stock_name", "product_name")
        or _first_text(order, "stockName", "productName", "stock_name", "product_name")
        or _material_code(order, item, stage=stage)
    )


def _unit(order: dict[str, Any]) -> str:
    return _first_text(order, "unit", "uom") or "AD"


def _work_order_label_payload(order: dict[str, Any]) -> dict[str, Any]:
    quantity = _quantity(order.get("quantity") or order.get("targetQty") or order.get("target_qty"))
    return {
        WORK_ORDER_LABEL_MAPPING["order_id"]: _first_text(order, "orderId", "order_id", "id"),
        WORK_ORDER_LABEL_MAPPING["quantity"]: quantity,
        WORK_ORDER_LABEL_MAPPING["date"]: _first_text(order, "date", "startedAt", "completedAt"),
        WORK_ORDER_LABEL_MAPPING["stock_code"]: _first_text(order, "stockCode", "productCode"),
        WORK_ORDER_LABEL_MAPPING["stock_name"]: _first_text(order, "stockName"),
        WORK_ORDER_LABEL_MAPPING["unit"]: _unit(order),
        WORK_ORDER_LABEL_MAPPING["work_center"]: _first_text(order, "workCenterCode"),
        WORK_ORDER_LABEL_MAPPING["work_station"]: _first_text(order, "workStationCode"),
        WORK_ORDER_LABEL_MAPPING["operation"]: _first_text(order, "operationCode"),
        WORK_ORDER_LABEL_MAPPING["cycle_time_sec"]: order.get("cycleTimeSec") or "",
    }


def build_station_flow(work_order: dict[str, Any], items: Any) -> list[dict[str, Any]]:
    order_id = _first_text(work_order, "orderId", "order_id", "id")
    flow: list[dict[str, Any]] = []
    for index, item in enumerate(_linked_items(items, order_id), start=1):
        for step in STATION_FLOW_TEMPLATE:
            event_at = _first_text(item, *step["event_fields"])
            if not event_at:
                continue
            flow.append(
                {
                    "station_id": step["station_id"],
                    "item_id": _item_id(item, index),
                    "event_at": event_at,
                    "input_stage": step["input_stage"],
                    "output_stage": step["output_stage"],
                    "classification": _classification(item.get("classification")),
                }
            )
    return flow


def _movement_header(
    *,
    object_code: str,
    screen: str,
    order_id: str,
    date_text: str,
    description: str,
    warehouse: str = "MES",
    location: str = "",
    warehouse_out: str = "",
    warehouse_in: str = "",
    location_out: str = "",
    location_in: str = "",
) -> dict[str, Any]:
    labels = {
        MATERIAL_MOVEMENT_LABEL_MAPPING["date"]: date_text,
        MATERIAL_MOVEMENT_LABEL_MAPPING["reference_number"]: order_id,
        MATERIAL_MOVEMENT_LABEL_MAPPING["description"]: description,
    }
    if object_code in {"mym2008", "mym2010"}:
        labels[MATERIAL_MOVEMENT_LABEL_MAPPING["warehouse"]] = warehouse
        if location:
            labels[MATERIAL_MOVEMENT_LABEL_MAPPING["location"]] = location
    if object_code == "mym2056":
        labels[MATERIAL_MOVEMENT_LABEL_MAPPING["warehouse_out"]] = warehouse_out or warehouse
        labels[MATERIAL_MOVEMENT_LABEL_MAPPING["warehouse_in"]] = warehouse_in or warehouse
        labels[MATERIAL_MOVEMENT_LABEL_MAPPING["location_out"]] = location_out or "SENSOR-01"
        labels[MATERIAL_MOVEMENT_LABEL_MAPPING["location_in"]] = location_in or "ROBOT-01"
    return {
        "ferp_object": object_code,
        "ferp_screen": screen,
        "ferp_labels": labels,
        "lines": [],
    }


def _movement_line(
    *,
    order: dict[str, Any],
    items: list[dict[str, Any]],
    stage: str,
    classification: str,
    qty: int,
) -> dict[str, Any]:
    sample = items[0] if items else {}
    labels = {
        MATERIAL_MOVEMENT_LABEL_MAPPING["material_code"]: _material_code(order, sample, stage=stage),
        MATERIAL_MOVEMENT_LABEL_MAPPING["material_name"]: _material_name(order, sample, stage=stage),
        MATERIAL_MOVEMENT_LABEL_MAPPING["unit"]: _unit(order),
    }
    return {
        "stage": stage,
        "classification": classification,
        "qty": qty,
        "item_ids": [_item_id(item, index) for index, item in enumerate(items, start=1)],
        "ferp_labels": labels,
    }


def _quality_summary(items: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"GOOD": 0, "REWORK": 0, "SCRAP": 0}
    for item in items:
        summary[_classification(item.get("classification"))] += 1
    summary["TOTAL"] = sum(summary.values())
    return summary


def _append_validation_warning(
    warnings: list[str],
    object_code: str,
    payload: dict[str, Any],
    *,
    registry_path: str | Path | None = None,
) -> None:
    validation = validate_label_payload(object_code, payload, registry_path)
    for warning in validation.get("warnings", []):
        warning_text = str(warning or "").strip()
        if warning_text and warning_text not in warnings:
            warnings.append(warning_text)


def build_ferp_documents(
    runtime_state: dict[str, Any],
    work_order: dict[str, Any],
    items: Any,
    *,
    registry_path: str | Path | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    del runtime_state
    order_id = _first_text(work_order, "orderId", "order_id", "id")
    date_text = _first_text(work_order, "completedAt", "autoCompletedAt", "date") or _iso_text()
    linked_items = _linked_items(items, order_id)
    summary = _quality_summary(linked_items)
    warnings = ["FERP_MATERIAL_QTY_LABEL_NOT_FOUND: material movement line qty is exported as qty."]

    raw_exit = _movement_header(
        object_code="mym2010",
        screen="Cikis Hareketleri",
        order_id=order_id,
        date_text=date_text,
        description=f"Raw material issue for {order_id}",
        warehouse="RAW",
        location="SENSOR-01",
    )
    if linked_items:
        raw_exit["lines"].append(
            _movement_line(
                order=work_order,
                items=linked_items,
                stage="RAW",
                classification="RAW_CONSUMED",
                qty=len(linked_items),
            )
        )

    material_entry = _movement_header(
        object_code="mym2008",
        screen="Giris Hareketleri",
        order_id=order_id,
        date_text=date_text,
        description=f"Production receipts for {order_id}",
        warehouse="FG",
        location="ROBOT-01",
    )
    if linked_items:
        material_entry["lines"].append(
            _movement_line(
                order=work_order,
                items=linked_items,
                stage="SEMI_FINISHED",
                classification="SEMI_FINISHED",
                qty=len(linked_items),
            )
        )
    for classification, stage in (("GOOD", "FINISHED_GOOD"), ("REWORK", "REWORK"), ("SCRAP", "SCRAP")):
        bucket = [item for item in linked_items if _classification(item.get("classification")) == classification]
        if not bucket:
            continue
        material_entry["lines"].append(
            _movement_line(
                order=work_order,
                items=bucket,
                stage=stage,
                classification=classification,
                qty=len(bucket),
            )
        )

    transfer = _movement_header(
        object_code="mym2056",
        screen="Onayli Depo Transferleri",
        order_id=order_id,
        date_text=date_text,
        description=f"Semi-finished transfer for {order_id}",
        warehouse="WIP",
        warehouse_out="WIP",
        warehouse_in="WIP",
        location_out="SENSOR-01",
        location_in="ROBOT-01",
    )
    if linked_items:
        transfer["lines"].append(
            _movement_line(
                order=work_order,
                items=linked_items,
                stage="SEMI_FINISHED_TRANSFER",
                classification="WIP_TRANSFER",
                qty=len(linked_items),
            )
        )

    documents = [raw_exit, material_entry, transfer]
    for document in documents:
        _append_validation_warning(warnings, document["ferp_object"], document["ferp_labels"], registry_path=registry_path)

    if summary["SCRAP"]:
        warnings.append("FERP_SCRAP_EXPORTED_SEPARATELY_FROM_FINISHED_GOOD")
    if summary["REWORK"]:
        warnings.append("FERP_REWORK_EXPORTED_AS_SEPARATE_LINE")
    return documents, warnings


def build_ferp_export_package(
    runtime_state: dict[str, Any],
    work_order: dict[str, Any],
    items: Any,
    *,
    module_id: str = "konveyor_main",
    created_at: Any = None,
    registry_path: str | Path | None = None,
    include_mes_runtime: bool = False,
) -> dict[str, Any]:
    order_id = _first_text(work_order, "orderId", "order_id", "id")
    created_at_text = _iso_text(created_at)
    object_code = _first_text(work_order, "ferpObject", "ferp_object") or "mym4004"
    screen = _first_text(work_order, "ferpScreen", "ferp_screen", "erpType") or "Is Emirleri"
    work_order_labels = _work_order_label_payload(work_order)
    linked_items = _linked_items(items, order_id)
    station_flow = build_station_flow(work_order, items)
    documents, warnings = build_ferp_documents(
        runtime_state,
        work_order,
        items,
        registry_path=registry_path,
    )
    _append_validation_warning(warnings, object_code, work_order_labels, registry_path=registry_path)
    export_id = f"FERP_{sanitize_filename_token(order_id)}_{safe_export_timestamp(created_at_text)}"

    package: dict[str, Any] = {
        "schema": EXPORT_SCHEMA,
        "export_id": export_id,
        "created_at": created_at_text,
        "source": {
            "system": "MES",
            "module_id": module_id,
        },
        "work_order": {
            "ferp_object": object_code,
            "ferp_screen": screen,
            "ferp_labels": work_order_labels,
        },
        "station_flow": station_flow,
        "ferp_documents": documents,
        "quality_summary": _quality_summary(linked_items),
        "warnings": warnings,
    }
    if include_mes_runtime:
        package["mes_runtime"] = {
            "order": dict(work_order),
            "item_count": len(linked_items),
        }
    return package


def write_ferp_export_package(package: dict[str, Any], pending_dir: str | Path) -> Path:
    target_dir = Path(pending_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    work_order = package.get("work_order") if isinstance(package.get("work_order"), dict) else {}
    labels = work_order.get("ferp_labels") if isinstance(work_order.get("ferp_labels"), dict) else {}
    order_id = labels.get(WORK_ORDER_LABEL_MAPPING["order_id"]) or package.get("export_id") or "UNKNOWN"
    timestamp = safe_export_timestamp(package.get("created_at"))
    base_name = f"FERP_{sanitize_filename_token(order_id)}_{timestamp}"
    candidate = target_dir / f"{base_name}.json"
    suffix = 2
    while candidate.exists():
        candidate = target_dir / f"{base_name}_{suffix}.json"
        suffix += 1
    candidate.write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return candidate

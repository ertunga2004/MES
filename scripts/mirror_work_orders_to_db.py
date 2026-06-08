from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mes_web.config import AppConfig
from mes_web.db.config import build_database_config


JsonObject = dict[str, Any]


UPSERT_SQL = """
INSERT INTO mes.work_orders (
    order_id,
    erp_type,
    status,
    product_code,
    target_quantity,
    started_at,
    completed_at,
    source_system,
    source_file,
    external_ref,
    payload,
    metadata,
    updated_at
) VALUES (
    %(order_id)s,
    %(erp_type)s,
    %(status)s,
    %(product_code)s,
    %(target_quantity)s,
    %(started_at)s,
    %(completed_at)s,
    %(source_system)s,
    %(source_file)s,
    %(external_ref)s,
    %(payload)s,
    %(metadata)s,
    now()
)
ON CONFLICT (order_id) DO UPDATE SET
    erp_type = EXCLUDED.erp_type,
    status = EXCLUDED.status,
    product_code = EXCLUDED.product_code,
    target_quantity = EXCLUDED.target_quantity,
    started_at = EXCLUDED.started_at,
    completed_at = EXCLUDED.completed_at,
    source_system = EXCLUDED.source_system,
    source_file = EXCLUDED.source_file,
    external_ref = EXCLUDED.external_ref,
    payload = EXCLUDED.payload,
    metadata = EXCLUDED.metadata,
    updated_at = now()
"""


def _resolve_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def _read_state_file(path: Path) -> JsonObject:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RuntimeError(f"Runtime state file not found: {path}") from exc
    except OSError as exc:
        raise RuntimeError(f"Runtime state file could not be read: {path} ({exc})") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Runtime state file is not valid JSON: {path} ({exc})") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Runtime state JSON root must be an object: {path}")
    return payload


def _text(value: Any) -> str:
    return str(value or "").strip()


def _nullable_text(value: Any) -> str | None:
    text = _text(value)
    return text or None


def _first_text(row: JsonObject, *names: str) -> str | None:
    for name in names:
        value = _nullable_text(row.get(name))
        if value is not None:
            return value
    return None


def _first_int(row: JsonObject, *names: str) -> int | None:
    for name in names:
        value = row.get(name)
        if value in (None, ""):
            continue
        try:
            return int(float(value))
        except (TypeError, ValueError):
            continue
    return None


def _timestamp_or_none(value: Any) -> str | None:
    text = _nullable_text(value)
    if text in {None, "0"}:
        return None
    return text


def _work_orders_payload(state: JsonObject) -> tuple[JsonObject, JsonObject]:
    work_orders = state.get("workOrders")
    if not isinstance(work_orders, dict):
        return {}, {}
    orders_by_id = work_orders.get("ordersById")
    return work_orders, orders_by_id if isinstance(orders_by_id, dict) else {}


def _build_mirror_rows(state_file: Path, state: JsonObject) -> list[JsonObject]:
    work_orders, orders_by_id = _work_orders_payload(state)
    source = work_orders.get("source") if isinstance(work_orders.get("source"), dict) else {}
    source_file = _first_text(source, "file", "sourceFile")
    source_system = "mes_web"
    rows: list[JsonObject] = []

    for order_key, raw_order in sorted(orders_by_id.items(), key=lambda item: str(item[0])):
        if not isinstance(raw_order, dict):
            continue
        order_id = _first_text(raw_order, "order_id", "orderId", "id") or _text(order_key)
        if not order_id:
            continue
        metadata = {
            "runtime_order_key": _text(order_key),
            "state_file": str(state_file),
            "source_folder": _nullable_text(source.get("folder")) if isinstance(source, dict) else None,
            "source_loaded_at": _nullable_text(source.get("loadedAt")) if isinstance(source, dict) else None,
            "completed_quantity": _first_int(raw_order, "completedQty", "completed_quantity"),
            "remaining_quantity": _first_int(raw_order, "remainingQty", "remaining_quantity"),
            "priority": _first_int(raw_order, "priority"),
            "planned_fields": {
                "queued_at": _nullable_text(raw_order.get("queuedAt")),
                "planned_start_at": _first_text(raw_order, "plannedStartAt", "planned_start_at"),
                "planned_end_at": _first_text(raw_order, "plannedEndAt", "planned_end_at"),
            },
        }
        rows.append(
            {
                "order_id": order_id,
                "erp_type": _first_text(raw_order, "erpType", "erp_type"),
                "status": _first_text(raw_order, "status"),
                "product_code": _first_text(raw_order, "productCode", "product_code", "productId", "stockCode"),
                "target_quantity": _first_int(raw_order, "targetQuantity", "targetQty", "quantity"),
                "started_at": _timestamp_or_none(_first_text(raw_order, "startedAt", "started_at")),
                "completed_at": _timestamp_or_none(_first_text(raw_order, "completedAt", "completed_at", "autoCompletedAt")),
                "source_system": source_system,
                "source_file": source_file,
                "external_ref": order_id,
                "payload": raw_order,
                "metadata": metadata,
            }
        )
    return rows


def _missing_or_suspicious(row: JsonObject) -> list[str]:
    warnings: list[str] = []
    if not row.get("order_id"):
        warnings.append("missing order_id")
    if not row.get("status"):
        warnings.append("missing status")
    if not row.get("product_code"):
        warnings.append("missing product_code")
    if row.get("target_quantity") is None:
        warnings.append("missing target_quantity")
    if not row.get("source_file"):
        warnings.append("missing source_file")
    return warnings


def _print_dry_run(rows: list[JsonObject], state_file: Path) -> None:
    print("MES work orders PostgreSQL mirror dry-run")
    print(f"state_file: {state_file}")
    print(f"work_order_count: {len(rows)}")
    print("db_writes: false")
    print()
    for row in rows:
        warnings = _missing_or_suspicious(row)
        print(f"- order_id={row['order_id']} external_ref={row['external_ref']}")
        print(f"  status={row.get('status') or ''} product_code={row.get('product_code') or ''}")
        print(f"  target_quantity={row.get('target_quantity')} source_file={row.get('source_file') or ''}")
        print(f"  suspicious={'; '.join(warnings) if warnings else '(none)'}")


def _import_psycopg() -> tuple[Any, Any]:
    try:
        import psycopg
        from psycopg.types.json import Jsonb
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is not installed") from exc
    return psycopg, Jsonb


def _apply_rows(rows: list[JsonObject], app_config: AppConfig) -> tuple[int, int]:
    db_config = build_database_config(app_config)
    if not db_config.enabled:
        raise RuntimeError("--apply requires MES_WEB_DB_ENABLED=true; no DB connection was opened.")
    psycopg, Jsonb = _import_psycopg()
    existing_order_ids: set[str] = set()
    inserted = 0
    updated = 0

    with psycopg.connect(**db_config.connection_kwargs()) as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT order_id FROM mes.work_orders")
                existing_order_ids = {str(row[0]) for row in cursor.fetchall()}
                for row in rows:
                    params = dict(row)
                    params["payload"] = Jsonb(row["payload"])
                    params["metadata"] = Jsonb(row["metadata"])
                    cursor.execute(UPSERT_SQL, params)
                    if row["order_id"] in existing_order_ids:
                        updated += 1
                    else:
                        inserted += 1
                        existing_order_ids.add(row["order_id"])
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return inserted, updated


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manual dry-run/apply mirror from MES runtime workOrders.ordersById to mes.work_orders."
    )
    parser.add_argument(
        "--state-file",
        help="Runtime state JSON path. Defaults to AppConfig.from_env().oee_runtime_state_path.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write to mes.work_orders. Requires MES_WEB_DB_ENABLED=true.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    app_config = AppConfig.from_env()
    state_file = _resolve_path(args.state_file) if args.state_file else _resolve_path(app_config.oee_runtime_state_path)

    try:
        state = _read_state_file(state_file)
        rows = _build_mirror_rows(state_file, state)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if not args.apply:
        _print_dry_run(rows, state_file)
        return 0

    if not rows:
        print("No work orders found; nothing to apply.")
        return 0

    print(f"Applying {len(rows)} work orders to mes.work_orders.")
    try:
        inserted, updated = _apply_rows(rows, app_config)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Work order mirror apply failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(f"Apply completed at {datetime.now(timezone.utc).isoformat()}")
    print(f"inserted={inserted}")
    print(f"updated={updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

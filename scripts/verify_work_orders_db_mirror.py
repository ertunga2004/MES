from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mes_web.config import AppConfig
from mes_web.db.config import build_database_config
from mes_web.db.connection import DatabaseDriverMissingError, database_connection


JsonObject = dict[str, Any]


WORK_ORDERS_SELECT_SQL = """
SELECT
    external_ref,
    status,
    product_code,
    target_quantity,
    source_file,
    payload
FROM mes.work_orders
ORDER BY external_ref
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


def _orders_by_id(state: JsonObject) -> tuple[JsonObject, JsonObject]:
    work_orders = state.get("workOrders")
    if not isinstance(work_orders, dict):
        return {}, {}
    orders = work_orders.get("ordersById")
    return work_orders, orders if isinstance(orders, dict) else {}


def _json_work_order_rows(state: JsonObject) -> dict[str, JsonObject]:
    work_orders, orders = _orders_by_id(state)
    source = work_orders.get("source") if isinstance(work_orders.get("source"), dict) else {}
    source_file = _first_text(source, "file", "sourceFile")
    rows: dict[str, JsonObject] = {}

    for order_key, raw_order in sorted(orders.items(), key=lambda item: str(item[0])):
        if not isinstance(raw_order, dict):
            continue
        order_id = _first_text(raw_order, "order_id", "orderId", "id") or _text(order_key)
        if not order_id:
            continue
        rows[order_id] = {
            "external_ref": order_id,
            "status": _first_text(raw_order, "status"),
            "product_code": _first_text(raw_order, "productCode", "product_code", "productId", "stockCode"),
            "target_quantity": _first_int(raw_order, "targetQuantity", "targetQty", "quantity"),
            "source_file": source_file,
            "payload": raw_order,
        }
    return rows


def _load_db_rows(app_config: AppConfig) -> dict[str, JsonObject]:
    db_config = build_database_config(app_config)
    if not db_config.enabled:
        raise RuntimeError("DB verification requires MES_WEB_DB_ENABLED=true")

    rows: dict[str, JsonObject] = {}
    with database_connection(db_config) as connection:
        if connection is None:
            raise RuntimeError("DB verification requires an enabled database connection")
        with connection.cursor() as cursor:
            cursor.execute(WORK_ORDERS_SELECT_SQL)
            for external_ref, status, product_code, target_quantity, source_file, payload in cursor.fetchall():
                rows[str(external_ref)] = {
                    "external_ref": str(external_ref),
                    "status": status,
                    "product_code": product_code,
                    "target_quantity": int(target_quantity) if target_quantity is not None else None,
                    "source_file": source_file,
                    "payload": payload,
                }
    return rows


def _compare_rows(json_rows: dict[str, JsonObject], db_rows: dict[str, JsonObject]) -> JsonObject:
    json_refs = set(json_rows)
    db_refs = set(db_rows)
    matched = sorted(json_refs & db_refs)
    missing = sorted(json_refs - db_refs)
    extra = sorted(db_refs - json_refs)
    changed: list[JsonObject] = []
    summary = {
        "status": {"matched": 0, "changed": 0},
        "product_code": {"matched": 0, "changed": 0},
        "target_quantity": {"matched": 0, "changed": 0},
        "source_file": {"matched": 0, "changed": 0},
        "payload_presence": {"matched": 0, "changed": 0},
    }

    for ref in matched:
        json_row = json_rows[ref]
        db_row = db_rows[ref]
        differences: list[str] = []
        for field in ("status", "product_code", "target_quantity", "source_file"):
            if json_row.get(field) == db_row.get(field):
                summary[field]["matched"] += 1
            else:
                summary[field]["changed"] += 1
                differences.append(field)

        json_payload_present = bool(json_row.get("payload"))
        db_payload_present = bool(db_row.get("payload"))
        if json_payload_present and db_payload_present:
            summary["payload_presence"]["matched"] += 1
        else:
            summary["payload_presence"]["changed"] += 1
            differences.append("payload_presence")

        if differences:
            changed.append({"external_ref": ref, "fields": differences})

    return {
        "json_work_order_count": len(json_rows),
        "db_work_order_count": len(db_rows),
        "matched_external_refs": matched,
        "missing_in_db": missing,
        "extra_in_db": extra,
        "changed_or_suspicious": changed,
        "field_comparison_summary": summary,
    }


def _print_report(report: JsonObject, state_file: Path) -> None:
    print("MES work orders DB mirror verification")
    print(f"state_file: {state_file}")
    print("db_writes: false")
    print(f"json_work_order_count: {report['json_work_order_count']}")
    print(f"db_work_order_count: {report['db_work_order_count']}")
    print(f"matched_external_refs: {len(report['matched_external_refs'])}")
    for ref in report["matched_external_refs"]:
        print(f"  - {ref}")
    print(f"missing_in_db: {len(report['missing_in_db'])}")
    for ref in report["missing_in_db"]:
        print(f"  - {ref}")
    print(f"extra_in_db: {len(report['extra_in_db'])}")
    for ref in report["extra_in_db"]:
        print(f"  - {ref}")
    print(f"changed_or_suspicious: {len(report['changed_or_suspicious'])}")
    for item in report["changed_or_suspicious"]:
        print(f"  - {item['external_ref']}: {', '.join(item['fields'])}")
    print("field_comparison_summary:")
    for field, counts in report["field_comparison_summary"].items():
        print(f"  {field}: matched={counts['matched']} changed={counts['changed']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only verification for MES runtime workOrders.ordersById against mes.work_orders."
    )
    parser.add_argument("--state-file", required=True, help="Runtime state JSON path.")
    parser.add_argument("--json", action="store_true", help="Print the verification report as JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state_file = _resolve_path(args.state_file)
    app_config = AppConfig.from_env()

    try:
        state = _read_state_file(state_file)
        json_rows = _json_work_order_rows(state)
        db_rows = _load_db_rows(app_config)
        report = _compare_rows(json_rows, db_rows)
    except DatabaseDriverMissingError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Work order DB mirror verification failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_report(report, state_file)

    if report["missing_in_db"] or report["extra_in_db"] or report["changed_or_suspicious"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

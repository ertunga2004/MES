from __future__ import annotations

from mes_web.config import AppConfig
from mes_web.db import work_order_mirror
from mes_web.db.work_order_mirror import (
    UPSERT_WORK_ORDER_SQL,
    WorkOrderMirrorResult,
    build_work_order_mirror_rows,
    mirror_work_orders_from_state,
)


def _sample_state() -> dict:
    return {
        "workOrders": {
            "source": {
                "folder": "C:/ferp",
                "file": "ferp_work_orders.json",
                "loadedAt": "2026-06-08T08:00:00+00:00",
            },
            "ordersById": {
                "WO-1": {
                    "orderId": "WO-1",
                    "erpType": "FERP",
                    "status": "queued",
                    "productCode": "PKT-RED",
                    "targetQuantity": 2,
                    "queuedAt": "2026-06-08T08:00:00+00:00",
                }
            },
        }
    }


def test_db_disabled_is_noop_without_upsert(monkeypatch) -> None:
    def fail_upsert(*_args, **_kwargs):
        raise AssertionError("upsert should not be called")

    monkeypatch.setattr(work_order_mirror, "_upsert_work_order_rows", fail_upsert)

    result = mirror_work_orders_from_state(
        AppConfig(db_enabled=False, db_mirror_work_orders=True),
        _sample_state(),
    )

    assert result.status == "disabled"
    assert result.attempted is False
    assert result.message == "MES_WEB_DB_ENABLED=false"


def test_mirror_flag_disabled_is_noop_without_upsert(monkeypatch) -> None:
    def fail_upsert(*_args, **_kwargs):
        raise AssertionError("upsert should not be called")

    monkeypatch.setattr(work_order_mirror, "_upsert_work_order_rows", fail_upsert)

    result = mirror_work_orders_from_state(
        AppConfig(db_enabled=True, db_mirror_work_orders=False),
        _sample_state(),
    )

    assert result.status == "disabled"
    assert result.attempted is False
    assert result.message == "MES_WEB_DB_MIRROR_WORK_ORDERS=false"


def test_two_flags_true_calls_upsert(monkeypatch) -> None:
    captured = {}

    def fake_upsert(config, rows):
        captured["config"] = config
        captured["rows"] = rows
        return WorkOrderMirrorResult(status="ok", attempted=True, row_count=len(rows), inserted=1, updated=0)

    monkeypatch.setattr(work_order_mirror, "_upsert_work_order_rows", fake_upsert)

    config = AppConfig(db_enabled=True, db_mirror_work_orders=True)
    result = mirror_work_orders_from_state(config, _sample_state())

    assert result.status == "ok"
    assert result.inserted == 1
    assert captured["config"] is config
    assert captured["rows"][0]["order_id"] == "WO-1"


def test_db_exception_does_not_escape_runtime_path(monkeypatch) -> None:
    def failing_upsert(*_args, **_kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(work_order_mirror, "_upsert_work_order_rows", failing_upsert)

    result = mirror_work_orders_from_state(
        AppConfig(db_enabled=True, db_mirror_work_orders=True),
        _sample_state(),
    )

    assert result.status == "error"
    assert result.attempted is True
    assert "db down" in result.message


def test_empty_or_missing_work_orders_is_safe_noop(monkeypatch) -> None:
    def fail_upsert(*_args, **_kwargs):
        raise AssertionError("upsert should not be called")

    monkeypatch.setattr(work_order_mirror, "_upsert_work_order_rows", fail_upsert)

    result = mirror_work_orders_from_state(
        AppConfig(db_enabled=True, db_mirror_work_orders=True),
        {"workOrders": {"ordersById": {}}},
    )

    assert result.status == "empty"
    assert result.attempted is False
    assert result.row_count == 0


def test_mapping_external_ref_and_order_id_are_stable() -> None:
    rows = build_work_order_mirror_rows(_sample_state(), state_file="logs/oee_runtime_state.json")

    assert len(rows) == 1
    row = rows[0]
    assert row["order_id"] == "WO-1"
    assert row["external_ref"] == "WO-1"
    assert row["erp_type"] == "FERP"
    assert row["status"] == "queued"
    assert row["product_code"] == "PKT-RED"
    assert row["target_quantity"] == 2
    assert row["source_system"] == "mes_web"
    assert row["source_file"] == "ferp_work_orders.json"
    assert row["metadata"]["runtime_order_key"] == "WO-1"
    assert row["metadata"]["state_file"] == "logs/oee_runtime_state.json"


def test_upsert_sql_targets_only_work_orders() -> None:
    lowered = UPSERT_WORK_ORDER_SQL.lower()

    assert "insert into mes.work_orders" in lowered
    assert "on conflict (order_id) do update" in lowered
    for forbidden in ("delete", "truncate", "drop", "alter"):
        assert forbidden not in lowered

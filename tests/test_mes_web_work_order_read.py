from __future__ import annotations

import unittest
from contextlib import contextmanager
from unittest.mock import patch

from mes_web.config import AppConfig
from mes_web.db import work_order_read
from mes_web.db.work_order_read import state_with_db_work_orders


def _fallback_state() -> dict:
    return {
        "lastUpdatedAt": "2026-06-16T09:00:00+00:00",
        "workOrders": {
            "source": {
                "system": "runtime_json",
                "file": "oee_runtime_state.json",
            },
            "activeOrderId": "WO-RUNTIME",
            "orderSequence": ["WO-RUNTIME"],
            "ordersById": {
                "WO-RUNTIME": {
                    "orderId": "WO-RUNTIME",
                    "status": "queued",
                    "stockCode": "OLD",
                    "quantity": 1,
                }
            },
            "packagingBuffer": {"itemsById": {"42": {"item_id": "42"}}},
        },
    }


def _fallback_active_state() -> dict:
    state = _fallback_state()
    state["workOrders"]["ordersById"]["WO-RUNTIME"]["status"] = "pending_approval"
    state["workOrders"]["ordersById"]["WO-RUNTIME"]["startedAt"] = "2026-06-16T09:01:00+00:00"
    state["workOrders"]["ordersById"]["WO-RUNTIME"]["autoCompletedAt"] = "2026-06-16T09:05:00+00:00"
    return state


class _Cursor:
    def __init__(self, rows: list[dict]) -> None:
        self.work_order_rows = rows
        self.rows = rows
        self.executed_sql = ""
        self.executed_sqls: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, sql: str, *_args) -> None:
        self.executed_sql = sql
        self.executed_sqls.append(sql)
        self.rows = [] if "FROM mes.station_queue" in sql else self.work_order_rows

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, rows: list[dict]) -> None:
        self.cursor_instance = _Cursor(rows)

    def cursor(self):
        return self.cursor_instance

    def close(self) -> None:
        return None


class WorkOrderReadTests(unittest.TestCase):
    def test_read_flag_disabled_keeps_runtime_state_and_does_not_connect(self) -> None:
        fallback = _fallback_state()

        with patch.object(
            work_order_read,
            "database_connection",
            side_effect=AssertionError("DB connection should not be opened"),
        ):
            result = state_with_db_work_orders(AppConfig(db_enabled=True, db_read_work_orders=False), fallback)

        self.assertEqual(result.status, "disabled")
        self.assertFalse(result.attempted)
        self.assertEqual(result.source, "runtime")
        self.assertIs(result.state, fallback)

    def test_db_work_orders_overlay_runtime_work_order_view(self) -> None:
        rows = [
            {
                "order_id": "WO-DB-1",
                "erp_type": "FERP",
                "status": "active",
                "product_code": "STK-RED",
                "target_quantity": 3,
                "started_at": "2026-06-16T09:05:00+00:00",
                "completed_at": None,
                "source_system": "mes_web",
                "source_file": "ferp_work_orders.json",
                "external_ref": "WO-DB-1",
                "payload": {
                    "orderId": "WO-DB-1",
                    "status": "queued",
                    "stockCode": "STK-RED",
                    "requirements": [],
                },
                "metadata": {"runtime_order_key": "WO-DB-1"},
                "created_at": "2026-06-16T09:04:00+00:00",
                "updated_at": "2026-06-16T09:05:00+00:00",
            }
        ]

        connection = _Connection(rows)

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(work_order_read, "database_connection", fake_connection):
            result = state_with_db_work_orders(AppConfig(db_enabled=True, db_read_work_orders=True), _fallback_state())

        work_orders = result.state["workOrders"]
        order = work_orders["ordersById"]["WO-DB-1"]
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.source, "postgresql")
        self.assertEqual(result.row_count, 1)
        self.assertTrue(any("FROM mes.work_orders" in sql for sql in connection.cursor_instance.executed_sqls))
        self.assertEqual(work_orders["source"]["table"], "mes.work_orders")
        self.assertEqual(work_orders["activeOrderId"], "WO-DB-1")
        self.assertEqual(work_orders["orderSequence"], ["WO-DB-1"])
        self.assertNotIn("WO-RUNTIME", work_orders["ordersById"])
        self.assertEqual(order["status"], "active")
        self.assertEqual(order["quantity"], 3)
        self.assertEqual(order["stockCode"], "STK-RED")
        self.assertEqual(order["stationCode"], "ASSEMBLY_01")
        self.assertEqual(order["_metadata"]["station_code"], "ASSEMBLY_01")
        self.assertEqual(work_orders["packagingBuffer"], {"itemsById": {"42": {"item_id": "42"}}})

    def test_db_station_queue_orders_work_orders_when_available(self) -> None:
        rows = [
            {
                "order_id": "WO-DB-1",
                "erp_type": "FERP",
                "status": "queued",
                "product_code": "BOX-RED",
                "target_quantity": 1,
                "started_at": None,
                "completed_at": None,
                "source_system": "mes_web",
                "source_file": "ferp_work_orders.json",
                "external_ref": "WO-DB-1",
                "payload": {"orderId": "WO-DB-1", "status": "queued", "stockCode": "BOX-RED"},
                "metadata": {"station_code": "ASSEMBLY_01", "queue_rank": 1},
                "created_at": "2026-06-16T09:04:00+00:00",
                "updated_at": "2026-06-16T09:05:00+00:00",
            },
            {
                "order_id": "WO-DB-2",
                "erp_type": "FERP",
                "status": "queued",
                "product_code": "BOX-BLUE",
                "target_quantity": 1,
                "started_at": None,
                "completed_at": None,
                "source_system": "mes_web",
                "source_file": "ferp_work_orders.json",
                "external_ref": "WO-DB-2",
                "payload": {"orderId": "WO-DB-2", "status": "queued", "stockCode": "BOX-BLUE"},
                "metadata": {"station_code": "ASSEMBLY_01", "queue_rank": 0},
                "created_at": "2026-06-16T09:04:00+00:00",
                "updated_at": "2026-06-16T09:05:00+00:00",
            },
        ]

        with patch.object(
            work_order_read,
            "_fetch_work_order_rows",
            return_value=rows,
        ), patch.object(
            work_order_read,
            "_fetch_station_queue_rows",
            return_value=[
                {"station_code": "ASSEMBLY_01", "order_id": "WO-DB-1", "queue_rank": 1, "status": "queued"},
                {"station_code": "ASSEMBLY_01", "order_id": "WO-DB-2", "queue_rank": 0, "status": "queued"},
            ],
        ):
            result = state_with_db_work_orders(AppConfig(db_enabled=True, db_read_work_orders=True), _fallback_state())

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.state["workOrders"]["orderSequence"], ["WO-DB-2", "WO-DB-1"])
        self.assertEqual(result.state["workOrders"]["source"]["queue_table"], "mes.station_queue")

    def test_db_station_queue_error_keeps_runtime_queue_fallback(self) -> None:
        rows = [
            {
                "order_id": "WO-DB-1",
                "erp_type": "FERP",
                "status": "queued",
                "product_code": "BOX-RED",
                "target_quantity": 1,
                "started_at": None,
                "completed_at": None,
                "source_system": "mes_web",
                "source_file": "ferp_work_orders.json",
                "external_ref": "WO-DB-1",
                "payload": {"orderId": "WO-DB-1", "status": "queued", "stockCode": "BOX-RED"},
                "metadata": {"station_code": "ASSEMBLY_01"},
                "created_at": "2026-06-16T09:04:00+00:00",
                "updated_at": "2026-06-16T09:05:00+00:00",
            }
        ]

        with patch.object(work_order_read, "_fetch_work_order_rows", return_value=rows), patch.object(
            work_order_read,
            "_fetch_station_queue_rows",
            side_effect=RuntimeError("missing station_queue"),
        ):
            result = state_with_db_work_orders(AppConfig(db_enabled=True, db_read_work_orders=True), _fallback_state())

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.state["workOrders"]["orderSequence"], ["WO-DB-1"])
        self.assertEqual(result.state["workOrders"]["source"]["queue_table"], "")

    def test_db_read_infers_station_code_when_metadata_is_missing(self) -> None:
        rows = [
            {
                "order_id": "WO-PKT-RED-001",
                "erp_type": "FERP",
                "status": "active",
                "product_code": "PKG_RED_3",
                "target_quantity": 1,
                "started_at": "2026-06-16T09:05:00+00:00",
                "completed_at": None,
                "source_system": "mes_web",
                "source_file": "ferp_work_orders.json",
                "external_ref": "WO-PKT-RED-001",
                "payload": {"orderId": "WO-PKT-RED-001", "status": "active", "stockCode": "PKG_RED_3"},
                "metadata": {},
                "created_at": "2026-06-16T09:04:00+00:00",
                "updated_at": "2026-06-16T09:05:00+00:00",
            },
            {
                "order_id": "TEST-FERP-REWORK",
                "erp_type": "FERP",
                "status": "queued",
                "product_code": "BOX-YEL",
                "target_quantity": 1,
                "started_at": None,
                "completed_at": None,
                "source_system": "mes_web",
                "source_file": "ferp_work_orders.json",
                "external_ref": "TEST-FERP-REWORK",
                "payload": {"orderId": "TEST-FERP-REWORK", "status": "queued", "stockCode": "BOX-YEL"},
                "metadata": {},
                "created_at": "2026-06-16T09:04:00+00:00",
                "updated_at": "2026-06-16T09:05:00+00:00",
            },
        ]
        connection = _Connection(rows)

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(work_order_read, "database_connection", fake_connection):
            result = state_with_db_work_orders(AppConfig(db_enabled=True, db_read_work_orders=True), _fallback_state())

        orders = result.state["workOrders"]["ordersById"]
        self.assertEqual(orders["WO-PKT-RED-001"]["stationCode"], "PACKAGING_01")
        self.assertEqual(orders["TEST-FERP-REWORK"]["stationCode"], "ASSEMBLY_01")

    def test_db_read_empty_result_falls_back_to_runtime_state(self) -> None:
        connection = _Connection([])

        @contextmanager
        def fake_connection(_config):
            yield connection

        fallback = _fallback_state()
        with patch.object(work_order_read, "database_connection", fake_connection):
            result = state_with_db_work_orders(AppConfig(db_enabled=True, db_read_work_orders=True), fallback)

        self.assertEqual(result.status, "fallback_empty")
        self.assertTrue(result.attempted)
        self.assertEqual(result.source, "runtime")
        self.assertIs(result.state, fallback)
        self.assertTrue(any("FROM mes.work_orders" in sql for sql in connection.cursor_instance.executed_sqls))

    def test_db_read_error_falls_back_to_runtime_state(self) -> None:
        @contextmanager
        def failing_connection(_config):
            raise RuntimeError("db down")
            yield None

        fallback = _fallback_state()
        with patch.object(work_order_read, "database_connection", failing_connection):
            result = state_with_db_work_orders(AppConfig(db_enabled=True, db_read_work_orders=True), fallback)

        self.assertEqual(result.status, "fallback_error")
        self.assertTrue(result.attempted)
        self.assertEqual(result.source, "runtime")
        self.assertIs(result.state, fallback)
        self.assertEqual(result.error_type, "RuntimeError")

    def test_db_read_falls_back_when_db_has_no_active_but_runtime_does(self) -> None:
        rows = [
            {
                "order_id": "WO-RUNTIME",
                "erp_type": "FERP",
                "status": "queued",
                "product_code": "PKT-RED",
                "target_quantity": 1,
                "started_at": None,
                "completed_at": None,
                "source_system": "mes_web",
                "source_file": "ferp_work_orders.json",
                "external_ref": "WO-RUNTIME",
                "payload": {
                    "orderId": "WO-RUNTIME",
                    "status": "queued",
                    "stockCode": "PKT-RED",
                },
                "metadata": {},
                "created_at": "2026-06-16T09:00:00+00:00",
                "updated_at": "2026-06-16T09:00:00+00:00",
            }
        ]
        connection = _Connection(rows)

        @contextmanager
        def fake_connection(_config):
            yield connection

        fallback = _fallback_active_state()
        with patch.object(work_order_read, "database_connection", fake_connection):
            result = state_with_db_work_orders(AppConfig(db_enabled=True, db_read_work_orders=True), fallback)

        self.assertEqual(result.status, "fallback_drift")
        self.assertEqual(result.source, "runtime")
        self.assertEqual(result.state["workOrders"]["activeOrderId"], "WO-RUNTIME")
        self.assertEqual(result.state["workOrders"]["ordersById"]["WO-RUNTIME"]["status"], "pending_approval")
        drift = result.state["workOrders"]["source"]["work_order_db_drift"]
        self.assertTrue(drift["detected"])
        self.assertEqual(drift["runtime_active_order_id"], "WO-RUNTIME")


if __name__ == "__main__":
    unittest.main()

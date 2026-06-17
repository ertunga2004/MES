from __future__ import annotations

import unittest
from unittest.mock import patch

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


class WorkOrderMirrorTests(unittest.TestCase):
    def test_db_disabled_is_noop_without_upsert(self) -> None:
        with patch.object(
            work_order_mirror,
            "_upsert_work_order_rows",
            side_effect=AssertionError("upsert should not be called"),
        ):
            result = mirror_work_orders_from_state(
                AppConfig(db_enabled=False, db_mirror_work_orders=True),
                _sample_state(),
            )

        self.assertEqual(result.status, "disabled")
        self.assertFalse(result.attempted)
        self.assertEqual(result.message, "MES_WEB_DB_ENABLED=false")

    def test_mirror_flag_disabled_is_noop_without_upsert(self) -> None:
        with patch.object(
            work_order_mirror,
            "_upsert_work_order_rows",
            side_effect=AssertionError("upsert should not be called"),
        ):
            result = mirror_work_orders_from_state(
                AppConfig(db_enabled=True, db_mirror_work_orders=False),
                _sample_state(),
            )

        self.assertEqual(result.status, "disabled")
        self.assertFalse(result.attempted)
        self.assertEqual(result.message, "MES_WEB_DB_MIRROR_WORK_ORDERS=false")

    def test_two_flags_true_calls_upsert(self) -> None:
        captured = {}

        def fake_upsert(config, rows):
            captured["config"] = config
            captured["rows"] = rows
            return WorkOrderMirrorResult(status="ok", attempted=True, row_count=len(rows), inserted=1, updated=0)

        with patch.object(work_order_mirror, "_upsert_work_order_rows", side_effect=fake_upsert):
            config = AppConfig(db_enabled=True, db_mirror_work_orders=True)
            result = mirror_work_orders_from_state(config, _sample_state())

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.inserted, 1)
        self.assertIs(captured["config"], config)
        self.assertEqual(captured["rows"][0]["order_id"], "WO-1")

    def test_db_read_flag_does_not_trigger_mirror_upsert(self) -> None:
        with patch.object(
            work_order_mirror,
            "_upsert_work_order_rows",
            side_effect=AssertionError("READ_WORK_ORDERS must not trigger upsert"),
        ):
            config = AppConfig(db_enabled=True, db_mirror_work_orders=False, db_read_work_orders=True)
            result = mirror_work_orders_from_state(config, _sample_state())

        self.assertEqual(result.status, "disabled")
        self.assertFalse(result.attempted)
        self.assertEqual(result.message, "MES_WEB_DB_MIRROR_WORK_ORDERS=false")

    def test_db_exception_does_not_escape_runtime_path(self) -> None:
        with patch.object(work_order_mirror, "_upsert_work_order_rows", side_effect=RuntimeError("db down")):
            result = mirror_work_orders_from_state(
                AppConfig(db_enabled=True, db_mirror_work_orders=True),
                _sample_state(),
            )

        self.assertEqual(result.status, "error")
        self.assertTrue(result.attempted)
        self.assertIn("db down", result.message)

    def test_empty_or_missing_work_orders_is_safe_noop(self) -> None:
        with patch.object(
            work_order_mirror,
            "_upsert_work_order_rows",
            side_effect=AssertionError("upsert should not be called"),
        ):
            result = mirror_work_orders_from_state(
                AppConfig(db_enabled=True, db_mirror_work_orders=True),
                {"workOrders": {"ordersById": {}}},
            )

        self.assertEqual(result.status, "empty")
        self.assertFalse(result.attempted)
        self.assertEqual(result.row_count, 0)

    def test_mapping_external_ref_and_order_id_are_stable(self) -> None:
        rows = build_work_order_mirror_rows(_sample_state(), state_file="logs/oee_runtime_state.json")

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["order_id"], "WO-1")
        self.assertEqual(row["external_ref"], "WO-1")
        self.assertEqual(row["erp_type"], "FERP")
        self.assertEqual(row["status"], "queued")
        self.assertEqual(row["product_code"], "PKT-RED")
        self.assertEqual(row["target_quantity"], 2)
        self.assertEqual(row["source_system"], "mes_web")
        self.assertEqual(row["source_file"], "ferp_work_orders.json")
        self.assertEqual(row["metadata"]["runtime_order_key"], "WO-1")
        self.assertEqual(row["metadata"]["state_file"], "logs/oee_runtime_state.json")

    def test_upsert_sql_targets_only_work_orders(self) -> None:
        lowered = UPSERT_WORK_ORDER_SQL.lower()

        self.assertIn("insert into mes.work_orders", lowered)
        self.assertIn("on conflict (order_id) do update", lowered)
        for forbidden in ("delete", "truncate", "drop", "alter"):
            self.assertNotIn(forbidden, lowered)

    def test_operational_reset_payload_preserves_planning_fields(self) -> None:
        payload = {
            "orderId": "TEST-FERP-SCRAP",
            "stockCode": "BOX-BLUE",
            "productCode": "BOX-BLUE",
            "stockName": "Mavi Test Kutusu",
            "quantity": 3,
            "remainingQty": 1,
            "status": "active",
            "startedAt": "2026-06-17T12:00:00+03:00",
            "completedQty": 2,
            "productionQty": 2,
            "inventoryConsumedQty": 0,
            "requirements": [
                {
                    "lineId": "blue",
                    "stockCode": "BOX-BLUE",
                    "productCode": "BOX-BLUE",
                    "quantity": 3,
                    "remainingQty": 1,
                    "completedQty": 2,
                    "productionQty": 2,
                    "inventoryConsumedQty": 0,
                }
            ],
        }

        reset = work_order_mirror._reset_payload_operational_fields(payload)

        self.assertEqual(reset["status"], "queued")
        self.assertEqual(reset["stockCode"], "BOX-BLUE")
        self.assertEqual(reset["productCode"], "BOX-BLUE")
        self.assertEqual(reset["quantity"], 3)
        self.assertEqual(reset["remainingQty"], 3)
        self.assertEqual(reset["completedQty"], 0)
        self.assertEqual(reset["productionQty"], 0)
        self.assertEqual(reset["inventoryConsumedQty"], 0)
        self.assertEqual(reset["startedAt"], "")
        self.assertEqual(reset["requirements"][0]["stockCode"], "BOX-BLUE")
        self.assertEqual(reset["requirements"][0]["productCode"], "BOX-BLUE")
        self.assertEqual(reset["requirements"][0]["quantity"], 3)
        self.assertEqual(reset["requirements"][0]["remainingQty"], 3)
        self.assertEqual(reset["requirements"][0]["completedQty"], 0)


if __name__ == "__main__":
    unittest.main()

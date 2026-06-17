from __future__ import annotations

import unittest
from unittest.mock import patch

from mes_web.config import AppConfig
from mes_web.db import package_bom_wip


class _FakeCursor:
    def __init__(self, rows=None, rowcount: int = 0) -> None:
        self.rows = list(rows or [])
        self.rowcount = rowcount
        self.sql = ""
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql, params=None) -> None:
        self.sql = str(sql)
        self.params = params

    def fetchall(self):
        return list(self.rows)


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor) -> None:
        self.cursor_obj = cursor
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def cursor(self):
        return self.cursor_obj

    def commit(self) -> None:
        self.commits += 1


class PackageBomWipTests(unittest.TestCase):
    def _config(self) -> AppConfig:
        config = AppConfig()
        object.__setattr__(config, "db_enabled", True)
        return config

    def test_runtime_available_rows_require_source_work_order_id(self) -> None:
        state = {
            "workOrders": {
                "packagingBuffer": {
                    "itemsById": {
                        "LEGACY-1": {
                            "item_id": "LEGACY-1",
                            "status": "available",
                            "classification": "GOOD",
                            "product_code": "RED_BOX",
                        },
                        "NEW-1": {
                            "item_id": "NEW-1",
                            "status": "available",
                            "classification": "GOOD",
                            "product_code": "RED_BOX",
                            "upstream_order_id": "TEST-FERP-RED",
                        },
                    },
                    "availableItemIds": ["LEGACY-1", "NEW-1"],
                }
            }
        }

        rows = package_bom_wip._runtime_available_component_rows(state)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_work_order_id"], "TEST-FERP-RED")
        self.assertEqual(rows[0]["source_item_id"], "NEW-1")

    def test_package_summary_uses_strict_available_wip_filter(self) -> None:
        config = self._config()
        bom_cursor = _FakeCursor(rows=[("RED_BOX", 1, "red")])
        count_cursor = _FakeCursor(rows=[])
        connections = iter([_FakeConnection(bom_cursor), _FakeConnection(count_cursor)])

        with patch.object(package_bom_wip, "database_connection", side_effect=lambda _config: next(connections)):
            availability = package_bom_wip.package_component_availability(
                config,
                {"workOrders": {"packagingBuffer": {"itemsById": {}, "availableItemIds": []}}},
                {"stockCode": "PKG_CUSTOM", "stockName": "Custom Paket"},
            )

        self.assertFalse(availability["can_start"])
        self.assertEqual(availability["components"][0]["available_qty"], 0)
        self.assertIn("source_work_order_id", count_cursor.sql)
        self.assertIn("source_item_id", count_cursor.sql)
        self.assertIn("reserved_by_order_id", count_cursor.sql)
        self.assertIn("consumed_by_package_id", count_cursor.sql)
        self.assertIn("consumed_at IS NULL", count_cursor.sql)

    def test_demo_package_bom_quantities_are_color_specific(self) -> None:
        config = self._config()
        state = {"workOrders": {"packagingBuffer": {"itemsById": {}, "availableItemIds": []}}}

        with patch.object(package_bom_wip, "_available_counts", return_value={"BLUE_BOX": 3, "RED_BOX": 2, "YELLOW_BOX": 1}):
            blue = package_bom_wip.package_component_availability(config, state, {"stockCode": "PKG_BLUE_3", "qty": 1})
            red = package_bom_wip.package_component_availability(config, state, {"stockCode": "PKG_RED_3", "qty": 1})
            yellow = package_bom_wip.package_component_availability(config, state, {"stockCode": "PKG_YELLOW_3", "qty": 1})

        self.assertEqual(blue["components"][0]["required_total"], 3)
        self.assertEqual(red["components"][0]["required_total"], 2)
        self.assertEqual(yellow["components"][0]["required_total"], 1)

    def test_reset_demo_package_wip_marks_available_rows_scrapped_and_is_idempotent(self) -> None:
        config = self._config()
        first_cursor = _FakeCursor(rowcount=2)
        second_cursor = _FakeCursor(rowcount=0)
        connections = iter([_FakeConnection(first_cursor), _FakeConnection(second_cursor)])

        with patch.object(package_bom_wip, "database_connection", side_effect=lambda _config: next(connections)):
            first_count = package_bom_wip.reset_demo_package_wip(config, reason="unit_test")
            second_count = package_bom_wip.reset_demo_package_wip(config, reason="unit_test")

        self.assertEqual(first_count, 2)
        self.assertEqual(second_count, 0)
        self.assertIn("status = 'scrapped'", first_cursor.sql)
        self.assertIn("status IN ('available', 'reserved')", first_cursor.sql)
        self.assertEqual(first_cursor.params["stock_codes"], ["RED_BOX", "BLUE_BOX", "YELLOW_BOX"])

    def test_reserve_package_components_uses_strict_eligibility_filter(self) -> None:
        config = self._config()
        cursor = _FakeCursor(rows=[(10, "BLUE_BOX", "ITEM-10")])

        with patch.object(package_bom_wip, "database_connection", return_value=_FakeConnection(cursor)):
            reserved = package_bom_wip.reserve_package_components(
                config,
                "WO-PKG-BLUE",
                "SESSION-1",
                {
                    "bom_configured": True,
                    "components": [{"component_stock_code": "BLUE_BOX", "required_qty": 1}],
                },
            )

        self.assertEqual(reserved[0]["source_item_id"], "ITEM-10")
        self.assertIn("source_work_order_id", cursor.sql)
        self.assertIn("source_item_id", cursor.sql)
        self.assertIn("reserved_by_order_id", cursor.sql)
        self.assertIn("consumed_by_package_id", cursor.sql)
        self.assertIn("consumed_at IS NULL", cursor.sql)


if __name__ == "__main__":
    unittest.main()

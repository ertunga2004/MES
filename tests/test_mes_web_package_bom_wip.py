from __future__ import annotations

import unittest
from unittest.mock import patch

from mes_web.config import AppConfig
from mes_web.db import package_bom_wip


class _FakeCursor:
    def __init__(self, fetches: list[list[tuple[object, ...]]] | None = None) -> None:
        self.queries: list[str] = []
        self.params: list[object] = []
        self._fetches = fetches if fetches is not None else [
            [("BLUE_BOX", 3, "blue")],
            [
                ("BLUE_BOX", 10, "ITEM-1"),
                ("BLUE_BOX", 11, "ITEM-2"),
                ("BLUE_BOX", 12, "ITEM-3"),
            ],
        ]

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, query: str, params: object = None) -> None:
        self.queries.append(query)
        self.params.append(params)

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._fetches.pop(0)


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor) -> None:
        self.cursor_obj = cursor

    def __enter__(self) -> "_FakeConnection":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return self.cursor_obj


class PackageBomWipTests(unittest.TestCase):
    def test_availability_requires_traceable_available_wip_and_multiplies_package_quantity(self) -> None:
        cursor = _FakeCursor()
        config = AppConfig(db_enabled=True)
        order = {"orderId": "WO-PKG-BLUE", "stockCode": "PKG_BLUE_3", "quantity": 1}

        with patch.object(package_bom_wip, "sync_runtime_package_wip", return_value=0), patch.object(
            package_bom_wip,
            "database_connection",
            return_value=_FakeConnection(cursor),
        ):
            availability = package_bom_wip.package_component_availability(config, {}, order)

        self.assertTrue(availability["can_start"])
        component = availability["components"][0]
        self.assertEqual(component["required_qty"], 3)
        self.assertEqual(component["required_total"], 3)
        self.assertEqual(component["available_qty"], 3)
        self.assertEqual(component["source_item_ids"], ["ITEM-1", "ITEM-2", "ITEM-3"])
        availability_sql = "\n".join(cursor.queries)
        self.assertIn("NULLIF(btrim(source_item_id), '') IS NOT NULL", availability_sql)
        self.assertIn("NULLIF(btrim(source_work_order_id), '') IS NOT NULL", availability_sql)
        self.assertIn("reserved_by_order_id IS NULL OR btrim(reserved_by_order_id) = ''", availability_sql)

    def test_package_order_quantity_supports_future_multi_package_orders(self) -> None:
        self.assertEqual(package_bom_wip.package_order_quantity({"quantity": 3}), 3)
        self.assertEqual(package_bom_wip.package_order_quantity({"target_quantity": 2}), 2)
        self.assertEqual(package_bom_wip.package_order_quantity({}), 1)

    def test_availability_blocks_when_required_total_exceeds_eligible_rows(self) -> None:
        cursor = _FakeCursor(
            fetches=[
                [("BLUE_BOX", 3, "blue")],
                [("BLUE_BOX", 10, "ITEM-1")],
            ]
        )
        config = AppConfig(db_enabled=True)
        order = {"orderId": "WO-PKG-BLUE", "stockCode": "PKG_BLUE_3", "quantity": 1}

        with patch.object(package_bom_wip, "sync_runtime_package_wip", return_value=0), patch.object(
            package_bom_wip,
            "database_connection",
            return_value=_FakeConnection(cursor),
        ):
            availability = package_bom_wip.package_component_availability(config, {}, order)

        self.assertFalse(availability["can_start"])
        detail = package_bom_wip.insufficient_components_detail(availability, "WO-PKG-BLUE")
        self.assertIsNotNone(detail)
        self.assertEqual(detail["code"], "PACKAGE_COMPONENTS_NOT_AVAILABLE")
        self.assertEqual(detail["components"][0]["missing_qty"], 2)

    def test_reserve_package_components_filters_legacy_untraceable_wip(self) -> None:
        cursor = _FakeCursor(fetches=[[("21", "BLUE_BOX", "ITEM-21", "WO-BLUE")]])
        availability = {
            "bom_configured": True,
            "components": [{"component_stock_code": "BLUE_BOX", "required_qty": 1}],
        }

        with patch.object(package_bom_wip, "database_connection", return_value=_FakeConnection(cursor)):
            reserved = package_bom_wip.reserve_package_components(
                AppConfig(db_enabled=True),
                "WO-PKG",
                "SESSION-1",
                availability,
            )

        self.assertEqual(reserved[0]["source_item_id"], "ITEM-21")
        self.assertEqual(reserved[0]["source_work_order_id"], "WO-BLUE")
        reserve_sql = "\n".join(cursor.queries)
        self.assertIn("NULLIF(btrim(source_item_id), '') IS NOT NULL", reserve_sql)
        self.assertIn("NULLIF(btrim(source_work_order_id), '') IS NOT NULL", reserve_sql)
        self.assertIn("consumed_at IS NULL", reserve_sql)


if __name__ == "__main__":
    unittest.main()

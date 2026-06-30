from __future__ import annotations

import unittest
from pathlib import Path

from mes_web.db.station_queue import (
    UPSERT_STATION_QUEUE_SQL,
    station_queue_params,
    station_queue_rows_from_work_order_rows,
    write_station_queue_row,
)


class StationQueueTests(unittest.TestCase):
    def test_migration_is_additive_and_defines_station_queue_keys(self) -> None:
        migration = Path(__file__).resolve().parents[1] / "db" / "migrations" / "006_station_queue.sql"
        script = migration.read_text(encoding="utf-8").lower()

        self.assertIn("create table if not exists mes.station_queue", script)
        self.assertIn("station_code text not null", script)
        self.assertIn("order_id text not null", script)
        self.assertIn("queue_rank integer not null", script)
        self.assertIn("uq_mes_station_queue_station_order", script)
        self.assertIn("uq_mes_station_queue_station_active_rank", script)
        for forbidden in ("drop ", "truncate "):
            self.assertNotIn(forbidden, script)

    def test_rows_are_ranked_per_station_from_work_order_metadata(self) -> None:
        rows = [
            {
                "order_id": "WO-PKG-2",
                "status": "queued",
                "product_code": "PKG_BLUE_3",
                "target_quantity": 1,
                "payload": {},
                "metadata": {"station_code": "PACKAGING_01", "queue_rank": 3},
            },
            {
                "order_id": "WO-ASM-1",
                "status": "active",
                "product_code": "BLUE_BOX",
                "target_quantity": 3,
                "payload": {},
                "metadata": {"station_code": "ASSEMBLY_01", "queue_rank": 2},
            },
            {
                "order_id": "WO-PKG-1",
                "status": "queued",
                "product_code": "PKG_RED_YELLOW",
                "target_quantity": 1,
                "payload": {},
                "metadata": {"station_code": "PACKAGING_01", "queue_rank": 1},
            },
        ]

        queue_rows = station_queue_rows_from_work_order_rows(rows)

        self.assertEqual(
            [(row.station_code, row.order_id, row.queue_rank, row.status) for row in queue_rows],
            [
                ("ASSEMBLY_01", "WO-ASM-1", 0, "active"),
                ("PACKAGING_01", "WO-PKG-1", 0, "queued"),
                ("PACKAGING_01", "WO-PKG-2", 1, "queued"),
            ],
        )

    def test_upsert_sql_is_duplicate_safe_and_non_destructive(self) -> None:
        lowered = UPSERT_STATION_QUEUE_SQL.lower()

        self.assertIn("insert into mes.station_queue", lowered)
        for forbidden in ("delete", "truncate", "drop", "alter"):
            self.assertNotIn(forbidden, lowered)

    def test_write_station_queue_row_skips_insert_when_active_rank_is_occupied(self) -> None:
        class Cursor:
            def __init__(self) -> None:
                self.executed: list[tuple[str, dict | None]] = []

            def execute(self, sql, params=None):
                self.executed.append((str(sql), params))

            def fetchone(self):
                sql = self.executed[-1][0]
                if "where station_code = %(station_code)s" in sql.lower() and "and order_id = %(order_id)s" in sql.lower():
                    return None
                if "and queue_rank = %(queue_rank)s" in sql.lower():
                    return ("WO-OTHER",)
                return None

        row = station_queue_rows_from_work_order_rows(
            [
                {
                    "order_id": "WO-1",
                    "status": "queued",
                    "payload": {},
                    "metadata": {"station_code": "ASSEMBLY_01", "queue_rank": 0},
                }
            ]
        )[0]
        cursor = Cursor()

        written = write_station_queue_row(cursor, row, jsonb=lambda value: value)

        self.assertFalse(written)
        self.assertFalse(any("insert into mes.station_queue" in sql.lower() for sql, _params in cursor.executed))

    def test_params_wrap_payload_and_metadata_as_jsonb(self) -> None:
        row = station_queue_rows_from_work_order_rows(
            [
                {
                    "order_id": "WO-1",
                    "status": "queued",
                    "payload": {},
                    "metadata": {"station_code": "ASSEMBLY_01", "queue_rank": 0},
                }
            ]
        )[0]

        params = station_queue_params(row, jsonb=lambda value: {"jsonb": value})

        self.assertEqual(params["station_code"], "ASSEMBLY_01")
        self.assertEqual(params["order_id"], "WO-1")
        self.assertEqual(params["queue_rank"], 0)
        self.assertEqual(params["payload"]["jsonb"]["order_id"], "WO-1")
        self.assertEqual(params["metadata"]["jsonb"]["work_order_metadata"]["station_code"], "ASSEMBLY_01")


if __name__ == "__main__":
    unittest.main()

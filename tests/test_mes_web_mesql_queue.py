from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mes_web.config import AppConfig
from mes_web.mesql_client import queue_plans
from mes_web.db import mesql_queue
from mes_web.db.mesql_queue import UPSERT_MESQL_STATION_QUEUE_SQL, UPSERT_MESQL_WORK_ORDER_SQL
from mes_web.oee_state import OeeRuntimeStateManager, default_runtime_state

from tests.test_mes_web_mesql_client import QUEUE_PAYLOAD


class _Transaction:
    def __init__(self, connection) -> None:
        self.connection = connection
        self.snapshot = None

    def __enter__(self):
        self.snapshot = (copy.deepcopy(self.connection.work_orders), copy.deepcopy(self.connection.station_queue))
        self.connection.transaction_count += 1
        return self

    def __exit__(self, exc_type, _exc, _tb):
        if exc_type is not None:
            self.connection.work_orders, self.connection.station_queue = self.snapshot
            self.connection.rollback_count += 1
        return False


class _Cursor:
    def __init__(self, connection) -> None:
        self.connection = connection
        self.result = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, sql, params=None):
        statement = " ".join(str(sql).lower().split())
        params = params or {}
        self.connection.executed.append((statement, copy.deepcopy(params)))
        if "pg_advisory_xact_lock" in statement:
            self.result = (None,)
        elif statement.startswith("select queue_rank"):
            row = next(
                (
                    row for row in self.connection.station_queue
                    if row["station_code"] == params["station_code"] and row["order_id"] == params["order_id"]
                ),
                None,
            )
            self.result = (row["queue_rank"],) if row else None
        elif statement.startswith("select coalesce(max(queue_rank)"):
            active_ranks = [
                row["queue_rank"] for row in self.connection.station_queue
                if row["station_code"] == params["station_code"]
                and row["status"] in {"queued", "active", "pending_approval"}
            ]
            self.result = ((max(active_ranks) if active_ranks else 0) + 1,)
        elif statement.startswith("insert into mes.work_orders"):
            current = self.connection.work_orders.get(params["order_id"])
            if current is None:
                self.connection.work_orders[params["order_id"]] = {
                    "order_id": params["order_id"],
                    "status": "queued",
                    "payload": copy.deepcopy(params["payload"]),
                    "metadata": copy.deepcopy(params["metadata"]),
                }
            else:
                current["payload"].update(copy.deepcopy(params["payload"]))
                current["metadata"].update(copy.deepcopy(params["metadata"]))
        elif statement.startswith("insert into mes.station_queue"):
            if self.connection.fail_station_insert:
                raise RuntimeError("uq_mes_station_queue_station_active_rank")
            current = next(
                (
                    row for row in self.connection.station_queue
                    if row["station_code"] == params["station_code"] and row["order_id"] == params["order_id"]
                ),
                None,
            )
            if current is None:
                if any(
                    row["station_code"] == params["station_code"]
                    and row["queue_rank"] == params["queue_rank"]
                    and row["status"] in {"queued", "active", "pending_approval"}
                    for row in self.connection.station_queue
                ):
                    raise RuntimeError("uq_mes_station_queue_station_active_rank")
                self.connection.station_queue.append({
                    "station_code": params["station_code"],
                    "order_id": params["order_id"],
                    "queue_rank": params["queue_rank"],
                    "status": "queued",
                    "payload": copy.deepcopy(params["queue_payload"]),
                    "metadata": copy.deepcopy(params["queue_metadata"]),
                })
            else:
                current["payload"].update(copy.deepcopy(params["queue_payload"]))
                current["metadata"].update(copy.deepcopy(params["queue_metadata"]))

    def fetchone(self):
        return self.result


class _Connection:
    def __init__(self, *, fail_station_insert: bool = False) -> None:
        self.work_orders = {f"LOCAL-{rank}": {"order_id": f"LOCAL-{rank}", "status": "queued", "payload": {}, "metadata": {}} for rank in range(1, 4)}
        statuses = ("queued", "active", "pending_approval")
        self.station_queue = [
            {
                "station_code": "ASSEMBLY_01",
                "order_id": f"LOCAL-{rank}",
                "queue_rank": rank,
                "status": statuses[rank - 1],
                "payload": {},
                "metadata": {},
            }
            for rank in range(1, 4)
        ]
        self.fail_station_insert = fail_station_insert
        self.executed = []
        self.transaction_count = 0
        self.rollback_count = 0

    def cursor(self):
        return _Cursor(self)

    def transaction(self):
        return _Transaction(self)


class MesqlQueueProtectionTests(unittest.TestCase):
    def test_sql_conflict_does_not_update_local_execution_columns(self) -> None:
        work_order_update = UPSERT_MESQL_WORK_ORDER_SQL.split("ON CONFLICT", 1)[1].lower()
        station_update = UPSERT_MESQL_STATION_QUEUE_SQL.split("ON CONFLICT", 1)[1].lower()

        for protected in (
            "status =", "started_at =", "completed_at =", "good_quantity =",
            "scrap_quantity =", "rework_quantity =", "oee =", "quality =",
            "downtime", "maintenance", "event",
        ):
            self.assertNotIn(protected, work_order_update)
        self.assertNotIn("status =", station_update)
        self.assertNotIn("queue_rank =", station_update)

    def test_db_writer_allocates_local_rank_and_preserves_it_on_repeat(self) -> None:
        connection = _Connection()
        plans = queue_plans(QUEUE_PAYLOAD)
        with patch.object(mesql_queue, "database_connection") as database_connection, patch.object(
            mesql_queue, "_jsonb", side_effect=lambda value: value
        ):
            database_connection.return_value.__enter__.return_value = connection
            first = mesql_queue.upsert_mesql_queue(AppConfig(db_enabled=True), plans)
            second = mesql_queue.upsert_mesql_queue(AppConfig(db_enabled=True), plans)

        self.assertTrue(first.success)
        self.assertTrue(second.success)
        mesql_rows = [row for row in connection.station_queue if row["order_id"] == "WO-MVP-002"]
        self.assertEqual(len(mesql_rows), 1)
        self.assertEqual(mesql_rows[0]["queue_rank"], 4)
        self.assertEqual(mesql_rows[0]["status"], "queued")
        self.assertEqual(mesql_rows[0]["metadata"]["mesql"]["remote_queue_rank"], 1)
        self.assertEqual(mesql_rows[0]["payload"]["mesql"]["remote_queue_rank"], 1)
        self.assertEqual(
            [(row["order_id"], row["queue_rank"], row["status"]) for row in connection.station_queue[:3]],
            [("LOCAL-1", 1, "queued"), ("LOCAL-2", 2, "active"), ("LOCAL-3", 3, "pending_approval")],
        )
        self.assertIn("WO-MVP-002", connection.work_orders)
        self.assertEqual(connection.transaction_count, 2)

    def test_station_queue_failure_rolls_back_work_order_insert_and_reports_error(self) -> None:
        connection = _Connection(fail_station_insert=True)
        with patch.object(mesql_queue, "database_connection") as database_connection, patch.object(
            mesql_queue, "_jsonb", side_effect=lambda value: value
        ):
            database_connection.return_value.__enter__.return_value = connection
            result = mesql_queue.upsert_mesql_queue(AppConfig(db_enabled=True), queue_plans(QUEUE_PAYLOAD))

        self.assertFalse(result.success)
        self.assertEqual(result.reason, "db_error")
        self.assertEqual(result.error_type, "RuntimeError")
        self.assertIn("uq_mes_station_queue_station_active_rank", result.error_message or "")
        self.assertNotIn("WO-MVP-002", connection.work_orders)
        self.assertEqual(connection.rollback_count, 1)

    def test_runtime_queue_merge_preserves_execution_state_and_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = OeeRuntimeStateManager(Path(temp_dir) / "runtime.json")
            state = default_runtime_state()
            state["workOrders"]["ordersById"] = {
                "WO-MVP-002": {
                    "orderId": "WO-MVP-002",
                    "status": "pending_approval",
                    "quantity": 3,
                    "completedQty": 3,
                    "productionQty": 3,
                    "remainingQty": 0,
                    "startedAt": "2026-06-19T10:00:00+03:00",
                    "completedAt": "",
                    "autoCompletedAt": "2026-06-19T10:10:00+03:00",
                    "goodQty": 2,
                    "reworkQty": 0,
                    "scrapQty": 1,
                    "runtimeMs": 600000,
                    "unplannedMs": 1000,
                    "quality": 66.7,
                    "oee": 60.0,
                    "transitionReason": "local reason",
                    "stationCode": "ASSEMBLY_01",
                    "operationNo": 10,
                    "requirements": [],
                }
            }
            state["workOrders"]["orderSequence"] = ["WO-MVP-002"]
            state["workOrders"]["activeOrderId"] = "WO-MVP-002"
            state["workOrders"]["transitionLog"] = [{"orderId": "WO-MVP-002", "eventType": "finished"}]
            state["maintenance"]["history"] = [{"sessionId": "LOCAL-MAINT"}]
            state["activeFault"] = {"faultId": "LOCAL-DOWNTIME", "status": "active"}
            manager.write_state(state)

            manager.merge_mesql_queue_plans(queue_plans(QUEUE_PAYLOAD))
            merged = manager.read_state()
            order = merged["workOrders"]["ordersById"]["WO-MVP-002"]

        self.assertEqual(order["status"], "pending_approval")
        self.assertEqual(order["startedAt"], "2026-06-19T10:00:00+03:00")
        self.assertEqual(order["goodQty"], 2)
        self.assertEqual(order["scrapQty"], 1)
        self.assertEqual(order["runtimeMs"], 600000)
        self.assertEqual(order["quality"], 66.7)
        self.assertEqual(order["oee"], 60.0)
        self.assertEqual(order["transitionReason"], "local reason")
        self.assertEqual(merged["workOrders"]["transitionLog"][0]["eventType"], "finished")
        self.assertEqual(merged["maintenance"]["history"][0]["sessionId"], "LOCAL-MAINT")
        self.assertEqual(merged["activeFault"]["faultId"], "LOCAL-DOWNTIME")
        self.assertEqual(order["_mesql"]["remote_status"], "queued")

    def test_new_remote_order_starts_with_local_queued_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = OeeRuntimeStateManager(Path(temp_dir) / "runtime.json")
            manager.write_state(default_runtime_state())

            manager.merge_mesql_queue_plans(queue_plans(QUEUE_PAYLOAD))
            order = manager.read_state()["workOrders"]["ordersById"]["WO-MVP-002"]

        self.assertEqual(order["status"], "queued")
        self.assertEqual(order["_mesql"]["remote_status"], "queued")


if __name__ == "__main__":
    unittest.main()

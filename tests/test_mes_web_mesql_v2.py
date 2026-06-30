from __future__ import annotations

import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import mes_web.app as app_module
from mes_web.config import AppConfig
from mes_web.db import mesql_v2
from mes_web.db.mesql_v2 import complete_operation_v2, read_station_queue_v2, start_operation_v2, upsert_mesql_queue_items
from mes_web.integration.mesql_pull import pull_mesql_station_queues
from mes_web.integration.mesql_push import push_mesql_outbox


class _Cursor:
    def __init__(self) -> None:
        self.executed: list[tuple[str, dict]] = []
        self.last_sql = ""
        self.last_params: dict = {}
        self.operation_status = "queued"
        self.queue_rows: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, sql: str, params: dict | None = None) -> None:
        self.last_sql = sql
        self.last_params = dict(params or {})
        self.executed.append((sql, dict(params or {})))

    def fetchone(self):
        lowered = self.last_sql.lower()
        if "from mes.work_order_operations" in lowered and "for update" in lowered:
            return {
                "work_order_operation_id": "11111111-1111-1111-1111-111111111111",
                "order_id": "WO-E2E-MAVI-001",
                "operation_no": 10,
                "operation_code": "OP-ASSEMBLY",
                "operation_name": "Assembly",
                "station_code": "ASSEMBLY_01",
                "status": self.operation_status,
                "planned_quantity": 1,
                "good_quantity": 0,
                "scrap_quantity": 0,
                "uom_code": "ADET",
                "started_at": None,
                "completed_at": None,
            }
        if "from mes.station_queue" in lowered and "for update" in lowered:
            return {"station_queue_pk": 7, "status": "queued"}
        if "from mes.work_order_operations" in lowered and "status in ('active'" in lowered:
            return None
        if "insert into mes.integration_outbox" in lowered:
            return {"outbox_id": "22222222-2222-2222-2222-222222222222"}
        if "returning work_order_operation_id" in lowered:
            return {"work_order_operation_id": "11111111-1111-1111-1111-111111111111"}
        if "select station_queue_pk" in lowered and "limit 1" in lowered:
            return None
        return None

    def fetchall(self):
        if "from mes.station_queue q" in self.last_sql.lower():
            return self.queue_rows
        return []


class _Connection:
    def __init__(self) -> None:
        self.cursor_instance = _Cursor()
        self.committed = False
        self.transaction_entered = False

    def cursor(self):
        return self.cursor_instance

    def transaction(self):
        connection = self

        class _Transaction:
            def __enter__(self):
                connection.transaction_entered = True
                return self

            def __exit__(self, *_args):
                return None

        return _Transaction()

    def commit(self) -> None:
        self.committed = True

    def close(self) -> None:
        return None


class _QueueConflictCursor:
    def __init__(self) -> None:
        self.executed: list[tuple[str, dict]] = []
        self.last_sql = ""

    def execute(self, sql: str, params: dict | None = None) -> None:
        self.last_sql = sql
        self.executed.append((sql, dict(params or {})))

    def fetchone(self):
        lowered = self.last_sql.lower()
        if "where station_code = %(station_code)s" in lowered and "and order_id = %(order_id)s" in lowered:
            return None
        if "queue_rank = %(queue_rank)s" in lowered and "order_id <> %(order_id)s" in lowered:
            return {"station_queue_pk": 99, "order_id": "WO-OTHER"}
        return None


class _FakeMesqlClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_station_queue(self, station_code: str) -> dict:
        self.calls.append(station_code)
        if station_code == "BROKEN_01":
            raise RuntimeError("network down")
        return {
            "station_code": station_code,
            "queue": [
                {
                    "station_code": station_code,
                    "order_id": "WO-E2E-MAVI-001",
                    "product_code": "PRD-MAVI",
                    "order_status": "queued",
                    "queue_status": "queued",
                    "queue_rank": 0,
                    "planned_quantity": 1,
                    "operation": {
                        "work_order_operation_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                        "operation_no": 10,
                        "operation_code": "OP-ASSEMBLY",
                        "operation_name": "Assembly",
                        "sequence_no": 10,
                        "station_code": station_code,
                        "status": "queued",
                    },
                }
            ],
        }


class MesqlV2Tests(unittest.TestCase):
    def test_migration_is_additive_and_defines_v2_tables(self) -> None:
        script = (Path(__file__).resolve().parents[1] / "db" / "migrations" / "008_mesql_integration_v2.sql").read_text(encoding="utf-8").lower()

        self.assertIn("create table if not exists mes.work_order_operations", script)
        self.assertIn("alter table mes.station_queue", script)
        self.assertIn("add column if not exists work_order_operation_id", script)
        self.assertIn("create table if not exists mes.packaging_units", script)
        self.assertIn("create table if not exists mes.integration_inbox", script)
        self.assertIn("create table if not exists mes.integration_outbox", script)
        self.assertNotIn("drop table", script)
        self.assertNotIn("drop column", script)

    def test_mesql_config_defaults_and_env(self) -> None:
        config = AppConfig.from_env()

        self.assertEqual(config.mesql_api_base_url, "http://ferptop:8090")
        self.assertEqual(config.mesql_stations, ("ASSEMBLY_01", "PACKAGING_01"))

    def test_pull_dry_run_maps_queue_items_without_db_write(self) -> None:
        item = {
            "station_code": "ASSEMBLY_01",
            "order_id": "WO-E2E-MAVI-001",
            "product_code": "PRD-MAVI",
            "order_status": "queued",
            "queue_status": "queued",
            "queue_rank": 0,
            "planned_quantity": 1,
            "operation": {
                "work_order_operation_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "operation_no": 10,
                "operation_code": "OP-ASSEMBLY",
                "operation_name": "Assembly",
                "sequence_no": 10,
                "station_code": "ASSEMBLY_01",
                "status": "queued",
            },
            "package_outputs": [{"package_no": "PKG-E2E-MAVI-001", "quantity": 1}],
        }

        result = upsert_mesql_queue_items(
            AppConfig(db_enabled=True),
            {"ASSEMBLY_01": [item]},
            dry_run=True,
        )

        self.assertEqual(result.upserted_work_orders, 1)
        self.assertEqual(result.upserted_operations, 1)
        self.assertEqual(result.upserted_queue_items, 1)
        self.assertEqual(result.upserted_packaging_units, 1)

    def test_pull_dry_run_does_not_model_package_as_separate_work_order(self) -> None:
        package_item = {
            "station_code": "PACKAGING_01",
            "order_id": "PKG-E2E-MAVI-001",
            "parent_order_id": "WO-E2E-MAVI-001",
            "product_code": "PRD-MAVI",
            "order_status": "queued",
            "queue_status": "queued",
            "queue_rank": 0,
            "planned_quantity": 1,
            "operation": {
                "work_order_operation_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                "operation_no": 20,
                "operation_code": "OP-PACKAGING",
                "operation_name": "Packaging",
                "sequence_no": 20,
                "station_code": "PACKAGING_01",
                "status": "queued",
            },
        }

        self.assertEqual(mesql_v2._canonical_order_id(package_item), "WO-E2E-MAVI-001")
        result = upsert_mesql_queue_items(
            AppConfig(db_enabled=True),
            {"PACKAGING_01": [package_item]},
            dry_run=True,
        )

        self.assertEqual(result.upserted_work_orders, 1)
        self.assertEqual(result.upserted_operations, 1)
        self.assertEqual(result.upserted_queue_items, 1)
        self.assertEqual(result.upserted_packaging_units, 1)

    def test_pull_dry_run_skips_package_item_without_parent_work_order(self) -> None:
        result = upsert_mesql_queue_items(
            AppConfig(db_enabled=True),
            {"PACKAGING_01": [{"station_code": "PACKAGING_01", "order_id": "PKG-E2E-MAVI-001"}]},
            dry_run=True,
        )

        self.assertEqual(result.upserted_work_orders, 0)
        self.assertEqual(result.skipped_items, 1)
        self.assertEqual(result.errors[0]["reason"], "package_parent_order_missing")

    def test_pull_adapter_reports_failed_station_without_counting_it_as_pulled(self) -> None:
        result = pull_mesql_station_queues(
            AppConfig(db_enabled=True),
            stations=["ASSEMBLY_01", "BROKEN_01"],
            dry_run=True,
            client=_FakeMesqlClient(),
        )

        self.assertEqual(result["pulled_station_count"], 1)
        self.assertEqual(result["upserted_work_orders"], 1)
        self.assertEqual(result["errors"][0]["station_code"], "BROKEN_01")

    def test_v2_queue_upsert_skips_new_item_when_active_rank_is_occupied(self) -> None:
        cursor = _QueueConflictCursor()

        written = mesql_v2._upsert_queue(
            cursor,
            {
                "station_code": "ASSEMBLY_01",
                "order_id": "WO-E2E-MAVI-001",
                "work_order_operation_id": "11111111-1111-1111-1111-111111111111",
                "queue_rank": 0,
                "status": "queued",
                "source": "mesql_pull",
                "payload": {},
                "metadata": {},
            },
        )

        self.assertFalse(written)
        self.assertFalse(any("insert into mes.station_queue" in sql.lower() for sql, _params in cursor.executed))

    def test_v2_queue_read_uses_local_db_shape(self) -> None:
        connection = _Connection()
        connection.cursor_instance.queue_rows = [
            {
                "station_code": "ASSEMBLY_01",
                "queue_rank": 0,
                "order_id": "WO-E2E-MAVI-001",
                "queue_status": "queued",
                "queue_payload": {},
                "queue_metadata": {},
                "product_code": "PRD-MAVI",
                "target_quantity": 1,
                "order_status": "queued",
                "order_started_at": None,
                "order_completed_at": None,
                "order_payload": {},
                "order_metadata": {},
                "work_order_operation_id": "11111111-1111-1111-1111-111111111111",
                "operation_no": 10,
                "operation_code": "OP-ASSEMBLY",
                "operation_name": "Assembly",
                "sequence_no": 10,
                "operation_status": "queued",
                "planned_quantity": 1,
                "good_quantity": 0,
                "scrap_quantity": 0,
                "uom_code": "ADET",
                "operation_started_at": None,
                "operation_completed_at": None,
                "operation_payload": {},
                "operation_metadata": {},
            }
        ]

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            queue = read_station_queue_v2(AppConfig(db_enabled=True), "ASSEMBLY_01")

        self.assertEqual(queue[0]["order_id"], "WO-E2E-MAVI-001")
        self.assertEqual(queue[0]["work_order_operation_id"], "11111111-1111-1111-1111-111111111111")
        self.assertEqual(queue[0]["operation_no"], 10)
        self.assertEqual(queue[0]["operation_status"], "queued")
        self.assertTrue(any("from mes.station_queue q" in sql.lower() for sql, _params in connection.cursor_instance.executed))

    def test_v2_routes_are_wired_to_db_authoritative_helpers(self) -> None:
        app = app_module.create_app()
        client = TestClient(app)
        self.addCleanup(client.close)

        with patch.object(
            app_module,
            "read_station_queue_v2",
            return_value=[
                {
                    "station_code": "ASSEMBLY_01",
                    "queue_rank": 0,
                    "order_id": "WO-E2E-MAVI-001",
                    "work_order_operation_id": "11111111-1111-1111-1111-111111111111",
                    "operation_no": 10,
                    "operation_status": "queued",
                }
            ],
        ):
            queue_response = client.get("/api/v2/stations/ASSEMBLY_01/queue")

        self.assertEqual(queue_response.status_code, 200)
        self.assertEqual(queue_response.json()["queue"][0]["work_order_operation_id"], "11111111-1111-1111-1111-111111111111")

        with patch.object(
            app_module,
            "start_operation_v2",
            return_value={
                "status": "ok",
                "order_id": "WO-E2E-MAVI-001",
                "work_order_operation_id": "11111111-1111-1111-1111-111111111111",
                "station_code": "ASSEMBLY_01",
                "operation_status": "active",
                "outbox_id": "22222222-2222-2222-2222-222222222222",
            },
        ) as start_helper:
            start_response = client.post(
                "/api/v2/stations/ASSEMBLY_01/operations/11111111-1111-1111-1111-111111111111/start",
                json={"actor_id": "OP-001"},
            )

        self.assertEqual(start_response.status_code, 200)
        self.assertEqual(start_response.json()["operation_status"], "active")
        self.assertEqual(start_helper.call_args.kwargs["work_order_operation_id"], "11111111-1111-1111-1111-111111111111")

    def test_start_operation_is_db_authoritative_and_writes_event_and_outbox(self) -> None:
        connection = _Connection()

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            result = start_operation_v2(
                AppConfig(db_enabled=True),
                station_code="ASSEMBLY_01",
                work_order_operation_id="11111111-1111-1111-1111-111111111111",
                actor_id="OP-001",
                started_at="2026-06-30T12:00:00+00:00",
            )

        executed_sql = "\n".join(sql.lower() for sql, _params in connection.cursor_instance.executed)
        self.assertEqual(result["operation_status"], "active")
        self.assertTrue(connection.transaction_entered)
        self.assertTrue(connection.committed)
        self.assertIn("update mes.work_order_operations", executed_sql)
        self.assertIn("update mes.work_orders", executed_sql)
        self.assertIn("update mes.station_queue", executed_sql)
        self.assertIn("insert into mes.work_order_events", executed_sql)
        self.assertIn("insert into mes.integration_outbox", executed_sql)

    def test_complete_operation_writes_completion_event_and_outbox(self) -> None:
        connection = _Connection()
        connection.cursor_instance.operation_status = "active"

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            result = complete_operation_v2(
                AppConfig(db_enabled=True),
                station_code="ASSEMBLY_01",
                work_order_operation_id="11111111-1111-1111-1111-111111111111",
                good_quantity=1,
                scrap_quantity=0,
                actor_id="OP-001",
                completed_at="2026-06-30T12:05:00+00:00",
            )

        executed_sql = "\n".join(sql.lower() for sql, _params in connection.cursor_instance.executed)
        executed_params = [params for _sql, params in connection.cursor_instance.executed]
        self.assertEqual(result["operation_status"], "completed")
        self.assertIn("insert into mes.production_completions", executed_sql)
        self.assertTrue(any(params.get("event_type") == "operation_completed" for params in executed_params))
        self.assertIn("insert into mes.integration_outbox", executed_sql)

    def test_push_dry_run_exposes_mesql_payload_without_http_call(self) -> None:
        event = mesql_v2.PendingOutboxEvent(
            outbox_id="22222222-2222-2222-2222-222222222222",
            event_type="operation_started",
            order_id="WO-E2E-MAVI-001",
            work_order_operation_id="11111111-1111-1111-1111-111111111111",
            station_code="ASSEMBLY_01",
            dedupe_key="mesql:operation_started:11111111-1111-1111-1111-111111111111",
            payload={
                "mesql_endpoint": "/api/v1/mes/operations/start",
                "mesql_request": {
                    "order_id": "WO-E2E-MAVI-001",
                    "operation_no": 10,
                    "operator_id": "OP-001",
                    "station_code": "ASSEMBLY_01",
                    "started_at": "2026-06-30T12:00:00+00:00",
                },
            },
        )

        with patch("mes_web.integration.mesql_push.pending_outbox_events", return_value=[event]):
            result = push_mesql_outbox(AppConfig(db_enabled=True), dry_run=True)

        self.assertEqual(result["read_count"], 1)
        self.assertEqual(result["pushed_count"], 0)
        self.assertEqual(result["dry_run_payloads"][0]["payload"]["order_id"], "WO-E2E-MAVI-001")


if __name__ == "__main__":
    unittest.main()

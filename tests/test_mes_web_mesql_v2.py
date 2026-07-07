from __future__ import annotations

import json
import unittest
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

from fastapi.testclient import TestClient

import mes_web.app as app_module
from mes_web.config import AppConfig
from mes_web.db import mesql_v2
from mes_web.db.mesql_v2 import (
    complete_operation_v2,
    get_location_by_code,
    get_station_location_context,
    list_locations,
    list_station_location_bindings,
    read_station_queue_v2,
    resolve_station_location,
    start_operation_v2,
    upsert_mesql_queue_items,
)
from mes_web.integration.mesql_pull import pull_mesql_station_queues
from mes_web.integration.mesql_push import push_mesql_outbox


class _Cursor:
    def __init__(self) -> None:
        self.executed: list[tuple[str, dict]] = []
        self.last_sql = ""
        self.last_params: dict = {}
        self.operation_status = "queued"
        self.planned_quantity = 1
        self.good_quantity = 0
        self.scrap_quantity = 0
        self.queue_rows: list[dict] = []
        self.location_rows: list[dict] = []
        self.location_row: dict | None = None
        self.binding_rows: list[dict] = []
        self.resolved_binding_row: dict | None = None

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
        if "from mes.locations" in lowered and "where location_code = %(location_code)s" in lowered:
            return self.location_row
        if "from mes.station_location_bindings b" in lowered and "join mes.locations l" in lowered and "limit 1" in lowered:
            return self.resolved_binding_row
        if "from mes.work_order_operations" in lowered and "sequence_no >" in lowered:
            return None
        if "from mes.work_order_operations" in lowered and "for update" in lowered:
            return {
                "work_order_operation_id": "11111111-1111-1111-1111-111111111111",
                "order_id": "WO-E2E-MAVI-001",
                "operation_no": 10,
                "sequence_no": 10,
                "operation_code": "OP-ASSEMBLY",
                "operation_name": "Assembly",
                "station_code": "ASSEMBLY_01",
                "status": self.operation_status,
                "planned_quantity": self.planned_quantity,
                "good_quantity": self.good_quantity,
                "scrap_quantity": self.scrap_quantity,
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
        lowered = self.last_sql.lower()
        if "from mes.locations" in lowered:
            return self.location_rows
        if "from mes.station_location_bindings b" in lowered:
            return self.binding_rows
        if "from mes.station_queue q" in lowered:
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


class _SuccessorCursor:
    ORDER_ID = "WO-LOCAL-SUCCESSOR-001"
    OP10_ID = "10101010-1010-1010-1010-101010101010"
    OP20_ID = "20202020-2020-2020-2020-202020202020"

    def __init__(self) -> None:
        self.executed: list[tuple[str, dict]] = []
        self.last_sql = ""
        self.last_params: dict = {}
        self.outbox_count = 0
        self.work_orders = {self.ORDER_ID: {"status": "active", "completed_at": None}}
        self.operations = {
            self.OP10_ID: {
                "work_order_operation_id": self.OP10_ID,
                "order_id": self.ORDER_ID,
                "operation_no": 10,
                "sequence_no": 10,
                "operation_code": "OP-ASSEMBLY",
                "operation_name": "Assembly",
                "station_code": "ASSEMBLY_01",
                "status": "active",
                "planned_quantity": 1,
                "good_quantity": 0,
                "scrap_quantity": 0,
                "uom_code": "ADET",
                "started_at": "2026-07-06T09:00:00+00:00",
                "completed_at": None,
            },
            self.OP20_ID: {
                "work_order_operation_id": self.OP20_ID,
                "order_id": self.ORDER_ID,
                "operation_no": 20,
                "sequence_no": 20,
                "operation_code": "OP-PACKAGING",
                "operation_name": "Packaging",
                "station_code": "PACKAGING_01",
                "status": "planned",
                "planned_quantity": 1,
                "good_quantity": 0,
                "scrap_quantity": 0,
                "uom_code": "ADET",
                "started_at": None,
                "completed_at": None,
            },
        }
        self.station_queue = [
            {
                "station_queue_pk": 1,
                "station_code": "ASSEMBLY_01",
                "order_id": self.ORDER_ID,
                "work_order_operation_id": self.OP10_ID,
                "queue_rank": 0,
                "status": "active",
            }
        ]
        self.next_queue_pk = 2

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, sql: str, params: dict | None = None) -> None:
        self.last_sql = sql
        self.last_params = dict(params or {})
        self.executed.append((sql, dict(params or {})))
        lowered = sql.lower()
        if "update mes.work_order_operations" in lowered and "set status = 'completed'" in lowered:
            operation = self.operations[self.last_params["work_order_operation_id"]]
            operation["status"] = "completed"
            operation["good_quantity"] = self.last_params["good_quantity"]
            operation["scrap_quantity"] = self.last_params["scrap_quantity"]
            operation["completed_at"] = self.last_params["completed_at"]
        elif "update mes.station_queue" in lowered and "set status = 'completed'" in lowered:
            row = self._queue_by_pk(self.last_params["station_queue_pk"])
            row["status"] = "completed"
        elif "update mes.work_order_operations" in lowered and "case" in lowered:
            operation = self.operations[self.last_params["work_order_operation_id"]]
            if operation["status"] not in {"completed", "done", "cancelled", "canceled", "active", "in_progress", "ready"}:
                operation["status"] = "queued"
        elif "insert into mes.station_queue" in lowered:
            row = {
                "station_queue_pk": self.next_queue_pk,
                "station_code": self.last_params["station_code"],
                "order_id": self.last_params["order_id"],
                "work_order_operation_id": self.last_params["work_order_operation_id"],
                "queue_rank": self.last_params["queue_rank"],
                "status": self.last_params["status"],
            }
            self.next_queue_pk += 1
            self.station_queue.append(row)
        elif "update mes.station_queue" in lowered and "where station_queue_pk = %(station_queue_pk)s" in lowered:
            row = self._queue_by_pk(self.last_params["station_queue_pk"])
            row.update(
                {
                    "station_code": self.last_params["station_code"],
                    "order_id": self.last_params["order_id"],
                    "work_order_operation_id": self.last_params["work_order_operation_id"],
                    "queue_rank": self.last_params["queue_rank"],
                    "status": self.last_params["status"],
                }
            )
        elif "update mes.work_orders w" in lowered:
            order_id = self.last_params["order_id"]
            if all(row["status"] in {"completed", "done"} for row in self.operations.values() if row["order_id"] == order_id):
                self.work_orders[order_id]["status"] = "completed"
                self.work_orders[order_id]["completed_at"] = self.last_params["completed_at"]

    def fetchone(self):
        lowered = self.last_sql.lower()
        if "from mes.work_order_operations" in lowered and "sequence_no >" in lowered:
            candidates = [
                row
                for row in self.operations.values()
                if row["order_id"] == self.last_params["order_id"]
                and row["sequence_no"] > self.last_params["sequence_no"]
                and row["status"] not in {"completed", "done", "cancelled", "canceled"}
            ]
            return min(candidates, key=lambda row: (row["sequence_no"], row["operation_no"])) if candidates else None
        if "from mes.work_order_operations" in lowered and "where work_order_operation_id" in lowered:
            return self.operations.get(self.last_params["work_order_operation_id"])
        if "from mes.station_queue" in lowered and " or (" in lowered:
            return self._queue_for_operation(self.last_params["station_code"], self.last_params["work_order_operation_id"])
        if "from mes.station_queue" in lowered and "work_order_operation_id = %(work_order_operation_id)s" in lowered:
            return self._queue_for_operation(self.last_params["station_code"], self.last_params["work_order_operation_id"])
        if "from mes.station_queue" in lowered and "work_order_operation_id is null" in lowered:
            for row in self.station_queue:
                if (
                    row["station_code"] == self.last_params["station_code"]
                    and row["order_id"] == self.last_params["order_id"]
                    and row["status"] in {"queued", "ready", "active", "pending_approval"}
                    and row["work_order_operation_id"] in {None, self.last_params["work_order_operation_id"]}
                ):
                    return row
            return None
        if "coalesce(max(queue_rank)" in lowered:
            ranks = [
                row["queue_rank"]
                for row in self.station_queue
                if row["station_code"] == self.last_params["station_code"]
                and row["status"] in {"queued", "ready", "active", "pending_approval"}
            ]
            return {"queue_rank": (max(ranks) + 1) if ranks else 0}
        if "insert into mes.integration_outbox" in lowered:
            self.outbox_count += 1
            return {"outbox_id": f"outbox-{self.outbox_count}"}
        return None

    def fetchall(self):
        return []

    def _queue_by_pk(self, station_queue_pk: int) -> dict:
        for row in self.station_queue:
            if row["station_queue_pk"] == station_queue_pk:
                return row
        raise AssertionError(f"missing station_queue_pk={station_queue_pk}")

    def _queue_for_operation(self, station_code: str, operation_id: str) -> dict | None:
        for row in self.station_queue:
            if row["station_code"] == station_code and row["work_order_operation_id"] == operation_id:
                return row
        return None


class _SuccessorConnection:
    def __init__(self) -> None:
        self.cursor_instance = _SuccessorCursor()
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


def _assert_json_serializable_without_decimal(test_case: unittest.TestCase, value) -> None:
    json.dumps(value)
    if isinstance(value, dict):
        for child in value.values():
            _assert_json_serializable_without_decimal(test_case, child)
    elif isinstance(value, list):
        for child in value:
            _assert_json_serializable_without_decimal(test_case, child)
    else:
        test_case.assertNotIsInstance(value, Decimal)


def _payload_for(executed_params: list[dict], event_type: str) -> dict:
    for params in executed_params:
        if params.get("event_type") == event_type:
            payload = params.get("payload")
            return dict(payload) if isinstance(payload, dict) else {}
    return {}


def _assert_iso_timestamp(test_case: unittest.TestCase, value) -> None:
    test_case.assertIsInstance(value, str)
    test_case.assertTrue(value)
    datetime.fromisoformat(value)


def _fake_location(
    location_code: str,
    *,
    location_pk: int = 1,
    location_type: str = "buffer",
    station_code: str | None = None,
    active: bool = True,
    payload: dict | None = None,
    metadata: dict | None = None,
) -> dict:
    return {
        "location_pk": location_pk,
        "location_id": location_code,
        "location_code": location_code,
        "location_name": location_code.replace("_", " ").title(),
        "location_type": location_type,
        "parent_location_code": None,
        "station_code": station_code,
        "active": active,
        "source_system": "mes_web",
        "source_file": "003_add_station_locations",
        "external_ref": f"seed:location:{location_code}",
        "payload": payload,
        "metadata": metadata,
        "created_at": datetime(2026, 7, 6, 20, 25, 30),
        "updated_at": datetime(2026, 7, 6, 20, 25, 30),
    }


def _fake_binding(
    station_code: str,
    role: str,
    location_code: str,
    *,
    binding_pk: int = 1,
    priority: int = 100,
    active: bool = True,
    location: dict | None = None,
) -> dict:
    row = {
        "binding_pk": binding_pk,
        "binding_id": f"{station_code}:{role}:{location_code}",
        "station_code": station_code,
        "role": role,
        "location_code": location_code,
        "item_scope": None,
        "operation_scope": None,
        "priority": priority,
        "active": active,
        "binding_source_system": "mes_web",
        "binding_source_file": "003_add_station_locations",
        "binding_external_ref": f"seed:station_location_binding:{station_code}:{role}:{location_code}",
        "binding_payload": None,
        "binding_metadata": None,
        "binding_created_at": datetime(2026, 7, 6, 20, 25, 30),
        "binding_updated_at": datetime(2026, 7, 6, 20, 25, 30),
    }
    if location:
        row.update(
            {
                "location_pk": location["location_pk"],
                "location_id": location["location_id"],
                "joined_location_code": location["location_code"],
                "location_name": location["location_name"],
                "location_type": location["location_type"],
                "parent_location_code": location["parent_location_code"],
                "location_station_code": location["station_code"],
                "location_active": location["active"],
                "location_source_system": location["source_system"],
                "location_source_file": location["source_file"],
                "location_external_ref": location["external_ref"],
                "location_payload": location["payload"],
                "location_metadata": location["metadata"],
                "location_created_at": location["created_at"],
                "location_updated_at": location["updated_at"],
            }
        )
    return row


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

    def test_json_safe_normalizes_decimal_uuid_and_dates(self) -> None:
        value = mesql_v2._json_safe(
            {
                "integral_decimal": Decimal("1.0"),
                "fractional_decimal": Decimal("1.25"),
                "operation_id": UUID("11111111-1111-1111-1111-111111111111"),
                "created_at": datetime(2026, 6, 30, 12, 0, 0),
                "business_date": date(2026, 6, 30),
                "items": (Decimal("2.0"),),
            }
        )

        self.assertEqual(value["integral_decimal"], 1)
        self.assertEqual(value["fractional_decimal"], 1.25)
        self.assertEqual(value["operation_id"], "11111111-1111-1111-1111-111111111111")
        self.assertEqual(value["created_at"], "2026-06-30T12:00:00")
        self.assertEqual(value["business_date"], "2026-06-30")
        self.assertEqual(value["items"], [2])
        _assert_json_serializable_without_decimal(self, value)

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

    def test_list_locations_reads_active_locations_by_default(self) -> None:
        connection = _Connection()
        connection.cursor_instance.location_rows = [
            _fake_location("RAW_MATERIAL", location_type="raw_material", payload=None, metadata=None)
        ]

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            locations = list_locations(AppConfig(db_enabled=True))

        self.assertEqual(locations[0]["location_code"], "RAW_MATERIAL")
        self.assertEqual(locations[0]["location_type"], "raw_material")
        self.assertEqual(locations[0]["payload"], {})
        self.assertEqual(locations[0]["metadata"], {})
        self.assertEqual(connection.cursor_instance.last_params["active_only"], True)
        self.assertIsNone(connection.cursor_instance.last_params["location_type"])
        self.assertTrue(any("from mes.locations" in sql.lower() for sql, _params in connection.cursor_instance.executed))

    def test_list_locations_can_filter_by_location_type(self) -> None:
        connection = _Connection()
        connection.cursor_instance.location_rows = [
            _fake_location("BETWEEN_ASSEMBLY_PACKAGING", location_type="buffer")
        ]

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            locations = list_locations(AppConfig(db_enabled=True), location_type="BUFFER")

        self.assertEqual(locations[0]["location_type"], "buffer")
        self.assertEqual(connection.cursor_instance.last_params["location_type"], "buffer")

    def test_get_location_by_code_normalizes_code_and_maps_row(self) -> None:
        connection = _Connection()
        connection.cursor_instance.location_row = _fake_location(
            "RAW_MATERIAL",
            location_type="raw_material",
            payload=None,
            metadata=None,
        )

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            location = get_location_by_code(AppConfig(db_enabled=True), "raw_material")

        self.assertIsNotNone(location)
        self.assertEqual(location["location_code"], "RAW_MATERIAL")
        self.assertEqual(location["payload"], {})
        self.assertEqual(location["metadata"], {})
        self.assertEqual(connection.cursor_instance.last_params["location_code"], "RAW_MATERIAL")

    def test_get_location_by_code_returns_none_when_missing(self) -> None:
        connection = _Connection()

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            location = get_location_by_code(AppConfig(db_enabled=True), "missing_location")

        self.assertIsNone(location)
        self.assertEqual(connection.cursor_instance.last_params["location_code"], "MISSING_LOCATION")

    def test_list_station_location_bindings_filters_by_station_and_role(self) -> None:
        connection = _Connection()
        location = _fake_location("FINISHED_GOODS", location_pk=5, location_type="finished_goods")
        connection.cursor_instance.binding_rows = [
            _fake_binding("PACKAGING_01", "output_good", "FINISHED_GOODS", location=location)
        ]

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            bindings = list_station_location_bindings(
                AppConfig(db_enabled=True),
                "packaging_01",
                role="OUTPUT_GOOD",
            )

        self.assertEqual(connection.cursor_instance.last_params["station_code"], "PACKAGING_01")
        self.assertEqual(connection.cursor_instance.last_params["role"], "output_good")
        self.assertEqual(bindings[0]["station_code"], "PACKAGING_01")
        self.assertEqual(bindings[0]["role"], "output_good")
        self.assertEqual(bindings[0]["location"]["location_code"], "FINISHED_GOODS")
        self.assertEqual(bindings[0]["payload"], {})
        self.assertEqual(bindings[0]["metadata"], {})

    def test_list_station_location_bindings_joins_by_location_code(self) -> None:
        sql = mesql_v2.SELECT_STATION_LOCATION_BINDINGS_SQL.lower()
        join_line = next(line.strip() for line in sql.splitlines() if " on " in line.lower() or line.strip().startswith("on "))

        self.assertIn("l.location_code = b.location_code", join_line)
        self.assertNotIn("location_id", join_line)
        self.assertNotIn("location_pk", join_line)

    def test_resolve_station_location_joins_by_location_code_not_location_id(self) -> None:
        connection = _Connection()
        location = _fake_location("BETWEEN_ASSEMBLY_PACKAGING", location_pk=3, location_type="buffer")
        connection.cursor_instance.resolved_binding_row = _fake_binding(
            "ASSEMBLY_01",
            "output_buffer",
            "BETWEEN_ASSEMBLY_PACKAGING",
            location=location,
        )

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            resolved = resolve_station_location(
                AppConfig(db_enabled=True),
                "assembly_01",
                "OUTPUT_BUFFER",
                item_scope="",
                operation_scope="",
            )

        sql = connection.cursor_instance.last_sql.lower()
        join_line = next(line.strip() for line in sql.splitlines() if " on " in line.lower() or line.strip().startswith("on "))
        self.assertIn("l.location_code = b.location_code", join_line)
        self.assertNotIn("location_id", join_line)
        self.assertNotIn("location_pk", join_line)
        self.assertEqual(connection.cursor_instance.last_params["station_code"], "ASSEMBLY_01")
        self.assertEqual(connection.cursor_instance.last_params["role"], "output_buffer")
        self.assertIsNone(connection.cursor_instance.last_params["item_scope"])
        self.assertIsNone(connection.cursor_instance.last_params["operation_scope"])
        self.assertEqual(resolved["location_code"], "BETWEEN_ASSEMBLY_PACKAGING")

    def test_resolve_station_location_returns_none_when_missing(self) -> None:
        connection = _Connection()

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            resolved = resolve_station_location(AppConfig(db_enabled=True), "PACKAGING_01", "output_buffer")

        self.assertIsNone(resolved)

    def test_get_station_location_context_groups_roles(self) -> None:
        connection = _Connection()
        connection.cursor_instance.binding_rows = [
            _fake_binding("ASSEMBLY_01", "input", "RAW_MATERIAL", location=_fake_location("RAW_MATERIAL", location_pk=1, location_type="raw_material")),
            _fake_binding("ASSEMBLY_01", "active_wip", "ASSEMBLY_WIP", location=_fake_location("ASSEMBLY_WIP", location_pk=2, location_type="wip", station_code="ASSEMBLY_01")),
            _fake_binding("ASSEMBLY_01", "output_good", "BETWEEN_ASSEMBLY_PACKAGING", location=_fake_location("BETWEEN_ASSEMBLY_PACKAGING", location_pk=3, location_type="buffer")),
            _fake_binding("ASSEMBLY_01", "output_scrap", "SCRAP_AREA", location=_fake_location("SCRAP_AREA", location_pk=4, location_type="scrap")),
            _fake_binding("ASSEMBLY_01", "output_buffer", "BETWEEN_ASSEMBLY_PACKAGING", binding_pk=5, location=_fake_location("BETWEEN_ASSEMBLY_PACKAGING", location_pk=3, location_type="buffer")),
        ]

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            context = get_station_location_context(AppConfig(db_enabled=True), "assembly_01")

        self.assertEqual(context["station_code"], "ASSEMBLY_01")
        self.assertEqual(context["input_location"]["location_code"], "RAW_MATERIAL")
        self.assertEqual(context["active_wip_location"]["location_code"], "ASSEMBLY_WIP")
        self.assertEqual(context["output_good_location"]["location_code"], "BETWEEN_ASSEMBLY_PACKAGING")
        self.assertEqual(context["output_buffer_location"]["location_code"], "BETWEEN_ASSEMBLY_PACKAGING")
        self.assertIn("input", context["locations_by_role"])
        self.assertEqual(context["missing_roles"], [])

    def test_get_station_location_context_allows_missing_optional_output_buffer(self) -> None:
        connection = _Connection()
        connection.cursor_instance.binding_rows = [
            _fake_binding("PACKAGING_01", "input", "BETWEEN_ASSEMBLY_PACKAGING", location=_fake_location("BETWEEN_ASSEMBLY_PACKAGING", location_pk=3, location_type="buffer")),
            _fake_binding("PACKAGING_01", "active_wip", "PACKAGING_WIP", location=_fake_location("PACKAGING_WIP", location_pk=4, location_type="wip", station_code="PACKAGING_01")),
            _fake_binding("PACKAGING_01", "output_good", "FINISHED_GOODS", location=_fake_location("FINISHED_GOODS", location_pk=5, location_type="finished_goods")),
            _fake_binding("PACKAGING_01", "output_scrap", "SCRAP_AREA", location=_fake_location("SCRAP_AREA", location_pk=6, location_type="scrap")),
        ]

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            context = get_station_location_context(AppConfig(db_enabled=True), "PACKAGING_01")

        self.assertIsNone(context["output_buffer_location"])
        self.assertNotIn("output_buffer", context["missing_roles"])
        self.assertEqual(context["missing_roles"], [])

    def test_station_location_read_helpers_do_not_execute_write_sql(self) -> None:
        read_sql_constants = [
            mesql_v2.SELECT_LOCATIONS_SQL,
            mesql_v2.SELECT_LOCATION_BY_CODE_SQL,
            mesql_v2.SELECT_STATION_LOCATION_BINDINGS_SQL,
            mesql_v2.SELECT_RESOLVE_STATION_LOCATION_SQL,
        ]
        forbidden_keywords = ("insert", "update", "delete", "drop", "truncate", "alter", "create")

        for sql in read_sql_constants:
            lowered = sql.lower()
            self.assertTrue(lowered.lstrip().startswith("select"))
            self.assertIn("from mes.", lowered)
            self.assertNotIn("for update", lowered)
            for keyword in forbidden_keywords:
                self.assertNotRegex(lowered, rf"\b{keyword}\b")

        for sql in (mesql_v2.SELECT_STATION_LOCATION_BINDINGS_SQL, mesql_v2.SELECT_RESOLVE_STATION_LOCATION_SQL):
            lowered = sql.lower()
            self.assertIn("from mes.station_location_bindings", lowered)
            self.assertIn("from mes.locations", lowered.replace("join", "from"))
            join_line = next(line.strip() for line in lowered.splitlines() if " on " in line.lower() or line.strip().startswith("on "))
            self.assertIn("l.location_code = b.location_code", join_line)
            self.assertNotIn("location_id", join_line)
            self.assertNotIn("location_pk", join_line)

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
            )

        executed_sql = "\n".join(sql.lower() for sql, _params in connection.cursor_instance.executed)
        executed_params = [params for _sql, params in connection.cursor_instance.executed]
        self.assertEqual(result["operation_status"], "active")
        self.assertTrue(connection.transaction_entered)
        self.assertTrue(connection.committed)
        self.assertIn("update mes.work_order_operations", executed_sql)
        self.assertIn("update mes.work_orders", executed_sql)
        self.assertIn("update mes.station_queue", executed_sql)
        self.assertIn("insert into mes.work_order_events", executed_sql)
        self.assertIn("insert into mes.integration_outbox", executed_sql)
        outbox_payload = _payload_for(executed_params, "operation_started")
        started_at = outbox_payload["mesql_request"]["started_at"]
        _assert_iso_timestamp(self, started_at)
        self.assertEqual(
            [params["started_at"] for params in executed_params if "started_at" in params],
            [started_at, started_at],
        )
        self.assertTrue(any(params.get("event_at") == started_at for params in executed_params))
        _assert_json_serializable_without_decimal(self, outbox_payload)

    def test_complete_operation_writes_completion_event_and_outbox(self) -> None:
        connection = _Connection()
        connection.cursor_instance.operation_status = "active"
        connection.cursor_instance.planned_quantity = Decimal("1.0")
        connection.cursor_instance.good_quantity = Decimal("0")
        connection.cursor_instance.scrap_quantity = Decimal("0")

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            result = complete_operation_v2(
                AppConfig(db_enabled=True),
                station_code="ASSEMBLY_01",
                work_order_operation_id="11111111-1111-1111-1111-111111111111",
                good_quantity=Decimal("1.0"),
                scrap_quantity=Decimal("0"),
                actor_id="OP-001",
                metadata={"measured_weight": Decimal("1.25")},
            )

        executed_sql = "\n".join(sql.lower() for sql, _params in connection.cursor_instance.executed)
        executed_params = [params for _sql, params in connection.cursor_instance.executed]
        self.assertEqual(result["operation_status"], "completed")
        self.assertIn("insert into mes.production_completions", executed_sql)
        self.assertTrue(any(params.get("event_type") == "operation_completed" for params in executed_params))
        self.assertIn("insert into mes.integration_outbox", executed_sql)
        json_payloads = [params["payload"] for params in executed_params if "payload" in params]
        self.assertTrue(json_payloads)
        for payload in json_payloads:
            _assert_json_serializable_without_decimal(self, payload)
        outbox_payload = _payload_for(executed_params, "operation_completed")
        completed_at = outbox_payload["mesql_request"]["completed_at"]
        _assert_iso_timestamp(self, completed_at)
        self.assertEqual(
            [params["completed_at"] for params in executed_params if "completed_at" in params],
            [completed_at, completed_at, completed_at],
        )
        self.assertTrue(any(params.get("event_at") == completed_at for params in executed_params))

    def test_complete_operation_activates_successor_once_and_final_operation_completes_order(self) -> None:
        connection = _SuccessorConnection()

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            first_result = complete_operation_v2(
                AppConfig(db_enabled=True),
                station_code="ASSEMBLY_01",
                work_order_operation_id=_SuccessorCursor.OP10_ID,
                good_quantity=1,
                scrap_quantity=0,
                actor_id="OP-001",
            )

            second_result = complete_operation_v2(
                AppConfig(db_enabled=True),
                station_code="ASSEMBLY_01",
                work_order_operation_id=_SuccessorCursor.OP10_ID,
                good_quantity=1,
                scrap_quantity=0,
                actor_id="OP-001",
            )

        cursor = connection.cursor_instance
        self.assertEqual(first_result["operation_status"], "completed")
        self.assertEqual(second_result["operation_status"], "completed")
        self.assertEqual(cursor.operations[_SuccessorCursor.OP10_ID]["status"], "completed")
        self.assertEqual(cursor.operations[_SuccessorCursor.OP20_ID]["status"], "queued")
        packaging_rows = [
            row
            for row in cursor.station_queue
            if row["station_code"] == "PACKAGING_01"
            and row["work_order_operation_id"] == _SuccessorCursor.OP20_ID
        ]
        self.assertEqual(len(packaging_rows), 1)
        self.assertEqual(packaging_rows[0]["status"], "queued")
        self.assertEqual(packaging_rows[0]["queue_rank"], 0)
        self.assertEqual(cursor.work_orders[_SuccessorCursor.ORDER_ID]["status"], "active")

        packaging_rows[0]["status"] = "active"
        cursor.operations[_SuccessorCursor.OP20_ID]["status"] = "active"

        with patch.object(mesql_v2, "database_connection", fake_connection):
            final_result = complete_operation_v2(
                AppConfig(db_enabled=True),
                station_code="PACKAGING_01",
                work_order_operation_id=_SuccessorCursor.OP20_ID,
                good_quantity=1,
                scrap_quantity=0,
                actor_id="OP-001",
            )

        self.assertEqual(final_result["operation_status"], "completed")
        self.assertEqual(cursor.operations[_SuccessorCursor.OP20_ID]["status"], "completed")
        self.assertEqual(cursor.work_orders[_SuccessorCursor.ORDER_ID]["status"], "completed")

    def test_complete_operation_skips_completed_successor_candidate(self) -> None:
        connection = _SuccessorConnection()
        cursor = connection.cursor_instance
        order_id = "WO-LOCAL-SUCCESSOR-SKIP-001"
        op10_id = "10101010-0000-0000-0000-000000000010"
        op20_id = "20202020-0000-0000-0000-000000000020"
        op30_id = "30303030-0000-0000-0000-000000000030"
        cursor.work_orders[order_id] = {"status": "active", "completed_at": None}
        cursor.operations.update(
            {
                op10_id: {
                    "work_order_operation_id": op10_id,
                    "order_id": order_id,
                    "operation_no": 10,
                    "sequence_no": 10,
                    "operation_code": "OP-ASSEMBLY",
                    "operation_name": "Assembly",
                    "station_code": "ASSEMBLY_01",
                    "status": "active",
                    "planned_quantity": 1,
                    "good_quantity": 0,
                    "scrap_quantity": 0,
                    "uom_code": "ADET",
                    "started_at": "2026-07-06T09:00:00+00:00",
                    "completed_at": None,
                },
                op20_id: {
                    "work_order_operation_id": op20_id,
                    "order_id": order_id,
                    "operation_no": 20,
                    "sequence_no": 20,
                    "operation_code": "OP-PACKAGING",
                    "operation_name": "Packaging",
                    "station_code": "PACKAGING_01",
                    "status": "completed",
                    "planned_quantity": 1,
                    "good_quantity": 1,
                    "scrap_quantity": 0,
                    "uom_code": "ADET",
                    "started_at": "2026-07-06T09:05:00+00:00",
                    "completed_at": "2026-07-06T09:10:00+00:00",
                },
                op30_id: {
                    "work_order_operation_id": op30_id,
                    "order_id": order_id,
                    "operation_no": 30,
                    "sequence_no": 30,
                    "operation_code": "OP-QUALITY",
                    "operation_name": "Quality",
                    "station_code": "QUALITY_01",
                    "status": "waiting",
                    "planned_quantity": 1,
                    "good_quantity": 0,
                    "scrap_quantity": 0,
                    "uom_code": "ADET",
                    "started_at": None,
                    "completed_at": None,
                },
            }
        )
        cursor.station_queue.append(
            {
                "station_queue_pk": cursor.next_queue_pk,
                "station_code": "ASSEMBLY_01",
                "order_id": order_id,
                "work_order_operation_id": op10_id,
                "queue_rank": 1,
                "status": "active",
            }
        )
        cursor.next_queue_pk += 1

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            complete_operation_v2(
                AppConfig(db_enabled=True),
                station_code="ASSEMBLY_01",
                work_order_operation_id=op10_id,
                good_quantity=1,
                scrap_quantity=0,
                actor_id="OP-001",
            )
            complete_operation_v2(
                AppConfig(db_enabled=True),
                station_code="ASSEMBLY_01",
                work_order_operation_id=op10_id,
                good_quantity=1,
                scrap_quantity=0,
                actor_id="OP-001",
            )

        self.assertEqual(cursor.operations[op20_id]["status"], "completed")
        self.assertEqual(cursor.operations[op30_id]["status"], "queued")
        quality_rows = [
            row
            for row in cursor.station_queue
            if row["station_code"] == "QUALITY_01"
            and row["work_order_operation_id"] == op30_id
        ]
        self.assertEqual(len(quality_rows), 1)
        self.assertEqual(quality_rows[0]["status"], "queued")

    def test_successor_query_orders_by_sequence_then_operation_number(self) -> None:
        self.assertIn(
            "ORDER BY sequence_no ASC, operation_no ASC",
            mesql_v2.SELECT_SUCCESSOR_OPERATION_SQL,
        )

    def test_push_dry_run_exposes_mesql_payload_without_http_call(self) -> None:
        start_event = mesql_v2.PendingOutboxEvent(
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
                    "good_quantity": Decimal("1.0"),
                    "started_at": "2026-06-30T12:00:00+00:00",
                },
            },
        )
        complete_event = mesql_v2.PendingOutboxEvent(
            outbox_id="33333333-3333-3333-3333-333333333333",
            event_type="operation_completed",
            order_id="WO-E2E-MAVI-001",
            work_order_operation_id="11111111-1111-1111-1111-111111111111",
            station_code="ASSEMBLY_01",
            dedupe_key="mesql:operation_completed:11111111-1111-1111-1111-111111111111",
            payload={
                "mesql_endpoint": "/api/v1/mes/operations/complete",
                "mesql_request": {
                    "order_id": "WO-E2E-MAVI-001",
                    "operation_no": 10,
                    "operator_id": "OP-001",
                    "station_code": "ASSEMBLY_01",
                    "good_quantity": Decimal("1.0"),
                    "scrap_quantity": Decimal("0"),
                    "completed_at": "2026-06-30T12:05:00+00:00",
                },
            },
        )

        with patch("mes_web.integration.mesql_push.pending_outbox_events", return_value=[start_event, complete_event]):
            result = push_mesql_outbox(AppConfig(db_enabled=True), dry_run=True)

        self.assertEqual(result["read_count"], 2)
        self.assertEqual(result["pushed_count"], 0)
        self.assertEqual(result["dry_run_payloads"][0]["payload"]["order_id"], "WO-E2E-MAVI-001")
        self.assertEqual(result["dry_run_payloads"][0]["payload"]["good_quantity"], 1)
        self.assertEqual(result["dry_run_payloads"][0]["payload"]["started_at"], "2026-06-30T12:00:00+00:00")
        self.assertEqual(result["dry_run_payloads"][1]["payload"]["completed_at"], "2026-06-30T12:05:00+00:00")
        self.assertEqual(result["dry_run_payloads"][1]["payload"]["good_quantity"], 1)
        self.assertEqual(result["dry_run_payloads"][1]["payload"]["scrap_quantity"], 0)
        _assert_json_serializable_without_decimal(self, result)


if __name__ == "__main__":
    unittest.main()

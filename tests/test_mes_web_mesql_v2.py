from __future__ import annotations

import json
import unittest
from copy import deepcopy
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
    finish_execution_step,
    get_execution_state,
    get_location_by_code,
    get_item_by_code,
    get_operation_event_by_external_event,
    get_operation_event_by_idempotency_key,
    get_operation_step,
    get_process_route,
    get_route_operation,
    get_route_operation_config,
    get_station_location_context,
    get_station_execution_config,
    initialize_execution_state,
    list_locations,
    list_execution_steps,
    list_items,
    list_operation_steps,
    list_process_routes,
    list_route_operations,
    list_station_event_sources,
    list_station_location_bindings,
    read_station_queue_v2,
    record_operation_event,
    resolve_station_event_source,
    resolve_station_location,
    start_execution_step,
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
        self.item_rows: list[dict] = []
        self.item_row: dict | None = None
        self.process_route_rows: list[dict] = []
        self.process_route_row: dict | None = None
        self.route_operation_rows: list[dict] = []
        self.route_operation_row: dict | None = None
        self.station_event_source_rows: list[dict] = []
        self.station_event_source_row: dict | None = None
        self.operation_step_rows: list[dict] = []
        self.operation_step_row: dict | None = None
        self.runtime_operation_row: dict | None = None
        self.execution_state_row: dict | None = None
        self.execution_step_rows: list[dict] = []
        self.operation_event_rows: list[dict] = []
        self.inserted_operation_event_row: dict | None = None
        self.station_exists = True
        self.raise_on_sql_fragment: str | None = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, sql: str, params: dict | None = None) -> None:
        self.last_sql = sql
        self.last_params = dict(params or {})
        self.executed.append((sql, dict(params or {})))
        lowered = sql.lower()
        if self.raise_on_sql_fragment and self.raise_on_sql_fragment in lowered:
            raise RuntimeError(f"forced cursor failure: {self.raise_on_sql_fragment}")
        if "insert into mes.work_order_operation_execution_state" in lowered:
            if self.execution_state_row is None:
                self.execution_state_row = {
                    "execution_state_id": self.last_params["execution_state_id"],
                    "work_order_operation_id": self.last_params["work_order_operation_id"],
                    "work_order_id": self.last_params["work_order_id"],
                    "station_code": self.last_params["station_code"],
                    "operation_code": self.last_params["operation_code"],
                    "execution_status": self.last_params["execution_status"],
                    "operation_completion_policy": self.last_params["operation_completion_policy"],
                    "current_step_code": self.last_params["current_step_code"],
                    "started_at": None,
                    "evidence_completed_at": None,
                    "pending_final_approval_at": None,
                    "closed_at": None,
                    "last_event_id": None,
                    "last_approval_id": None,
                    "created_at": None,
                    "updated_at": None,
                    "metadata": self.last_params["metadata"],
                }
        elif "insert into mes.work_order_operation_steps" in lowered:
            key = (
                self.last_params["work_order_operation_id"],
                self.last_params["step_code"],
            )
            if not any(
                (
                    row.get("work_order_operation_id"),
                    row.get("step_code"),
                ) == key
                for row in self.execution_step_rows
            ):
                self.execution_step_rows.append(
                    {
                        "work_order_operation_step_id": self.last_params["work_order_operation_step_id"],
                        "work_order_operation_id": self.last_params["work_order_operation_id"],
                        "work_order_id": self.last_params["work_order_id"],
                        "operation_code": self.last_params["operation_code"],
                        "step_code": self.last_params["step_code"],
                        "step_no": self.last_params["step_no"],
                        "station_code": self.last_params["station_code"],
                        "status": self.last_params["status"],
                        "started_at": None,
                        "completed_at": None,
                        "started_by_event_id": None,
                        "completed_by_event_id": None,
                        "required_for_completion": self.last_params["required_for_completion"],
                        "records_duration": self.last_params["records_duration"],
                        "approval_required_after_finish": self.last_params["approval_required_after_finish"],
                        "created_at": None,
                        "updated_at": None,
                        "metadata": self.last_params["metadata"],
                    }
                )
        elif "insert into mes.operation_events" in lowered:
            row = {
                "event_id": self.last_params["event_id"],
                "event_time": datetime(2026, 7, 9, 12, 0, 0),
                "received_at": datetime(2026, 7, 9, 12, 0, 1),
                "station_code": self.last_params["station_code"],
                "work_order_id": self.last_params["work_order_id"],
                "work_order_operation_id": self.last_params["work_order_operation_id"],
                "work_order_operation_step_id": self.last_params["work_order_operation_step_id"],
                "operation_code": self.last_params["operation_code"],
                "step_code": self.last_params["step_code"],
                "event_source": self.last_params["event_source"],
                "event_type": self.last_params["event_type"],
                "external_event_id": self.last_params["external_event_id"],
                "idempotency_key": self.last_params["idempotency_key"],
                "payload": _unwrap_json_value(self.last_params["payload"]),
                "accepted": self.last_params["accepted"],
                "rejection_reason": self.last_params["rejection_reason"],
                "created_at": datetime(2026, 7, 9, 12, 0, 1),
            }
            self.operation_event_rows.append(row)
            self.inserted_operation_event_row = row
        elif "update mes.work_order_operation_execution_state" in lowered:
            if self.execution_state_row is not None:
                self.execution_state_row["execution_status"] = self.last_params.get(
                    "execution_status",
                    "active",
                )
                self.execution_state_row["current_step_code"] = self.last_params["current_step_code"]
                event_time = self.last_params.get("event_time", datetime(2026, 7, 10, 9, 0, 0))
                self.execution_state_row["started_at"] = self.execution_state_row["started_at"] or event_time
                if self.last_params.get("completion_policy_applied"):
                    self.execution_state_row["evidence_completed_at"] = event_time
                    self.execution_state_row["pending_final_approval_at"] = (
                        event_time
                        if self.last_params.get("set_pending_final_approval_at")
                        else None
                    )
                    self.execution_state_row["closed_at"] = (
                        event_time
                        if self.last_params.get("set_closed_at")
                        else None
                    )
                self.execution_state_row["last_event_id"] = self.last_params["last_event_id"]
                self.execution_state_row["updated_at"] = event_time
        elif "update mes.work_order_operation_steps" in lowered:
            for row in self.execution_step_rows:
                if (
                    row.get("work_order_operation_id") == self.last_params["work_order_operation_id"]
                    and row.get("step_code") == self.last_params["step_code"]
                ):
                    if "status = 'completed'" in lowered:
                        event_time = self.last_params["event_time"]
                        row["status"] = "completed"
                        row["started_at"] = row["started_at"] or event_time
                        row["completed_at"] = event_time
                        row["started_by_event_id"] = row["started_by_event_id"] or self.last_params["event_id"]
                        row["completed_by_event_id"] = self.last_params["event_id"]
                        row["updated_at"] = event_time
                    else:
                        row["status"] = "active"
                        row["started_at"] = row["started_at"] or datetime(2026, 7, 10, 9, 0, 0)
                        row["started_by_event_id"] = row["started_by_event_id"] or self.last_params["started_by_event_id"]
                        row["updated_at"] = datetime(2026, 7, 10, 9, 0, 0)

    def fetchone(self):
        lowered = self.last_sql.lower()
        if "update mes.work_order_operation_steps" in lowered and "returning" in lowered:
            operation_id = self.last_params.get("work_order_operation_id")
            step_code = self.last_params.get("step_code")
            return next(
                (
                    row for row in self.execution_step_rows
                    if row.get("work_order_operation_id") == operation_id and row.get("step_code") == step_code
                ),
                None,
            )
        if "insert into mes.operation_events" in lowered and "returning" in lowered:
            return self.inserted_operation_event_row
        if "from mes.operation_events" in lowered and "idempotency_key = %(idempotency_key)s" in lowered:
            idempotency_key = self.last_params.get("idempotency_key")
            for row in self.operation_event_rows:
                if row.get("idempotency_key") == idempotency_key:
                    return row
            return None
        if "from mes.operation_events" in lowered and "external_event_id = %(external_event_id)s" in lowered:
            station_code = self.last_params.get("station_code")
            event_source = self.last_params.get("event_source")
            external_event_id = self.last_params.get("external_event_id")
            for row in self.operation_event_rows:
                if (
                    row.get("station_code") == station_code
                    and row.get("event_source") == event_source
                    and row.get("external_event_id") == external_event_id
                ):
                    return row
            return None
        if "from mes.work_order_operation_execution_state" in lowered:
            operation_id = self.last_params.get("work_order_operation_id")
            if self.execution_state_row and self.execution_state_row.get("work_order_operation_id") == operation_id:
                return self.execution_state_row
            return None
        if "from mes.work_order_operation_steps" in lowered:
            operation_id = self.last_params.get("work_order_operation_id")
            step_code = self.last_params.get("step_code")
            for row in self.execution_step_rows:
                if row.get("work_order_operation_id") == operation_id and row.get("step_code") == step_code:
                    return row
            return None
        if "from mes.work_order_operations" in lowered and "where work_order_operation_id = %(work_order_operation_id)s" in lowered and "for update" not in lowered:
            if self.runtime_operation_row is not None:
                return self.runtime_operation_row
            return {
                "work_order_operation_id": self.last_params.get("work_order_operation_id"),
                "order_id": "WO-E2E-MAVI-001",
                "operation_code": "OP10_ASSEMBLY_CLASSIFICATION",
                "station_code": "ASSEMBLY_01",
            }
        if "from mes.locations" in lowered and "where location_code = %(location_code)s" in lowered:
            return self.location_row
        if "from mes.station_location_bindings b" in lowered and "join mes.locations l" in lowered and "limit 1" in lowered:
            return self.resolved_binding_row
        if "from mes.items" in lowered and "where item_code = %(item_code)s" in lowered:
            item_code = self.last_params.get("item_code")
            for row in self.item_rows:
                if row.get("item_code") == item_code:
                    return row
            return self.item_row
        if "from mes.process_routes" in lowered and "where route_code = %(route_code)s" in lowered:
            route_code = self.last_params.get("route_code")
            version = self.last_params.get("version")
            for row in self.process_route_rows:
                if row.get("route_code") == route_code and row.get("version") == version:
                    return row
            return self.process_route_row
        if "from mes.route_operations" in lowered and "where route_operation_id = %(route_operation_id)s" in lowered:
            route_operation_id = self.last_params.get("route_operation_id")
            for row in self.route_operation_rows:
                if row.get("route_operation_id") == route_operation_id:
                    return row
            return self.route_operation_row
        if "from mes.station_event_sources" in lowered and "source_code = %(source_code)s" in lowered:
            station_code = self.last_params.get("station_code")
            source_code = self.last_params.get("source_code")
            for row in self.station_event_source_rows:
                if row.get("station_code") == station_code and row.get("source_code") == source_code:
                    return row
            return self.station_event_source_row
        if "from mes.operation_steps" in lowered and "step_code = %(step_code)s" in lowered:
            route_operation_id = self.last_params.get("route_operation_id")
            step_code = self.last_params.get("step_code")
            for row in self.operation_step_rows:
                if row.get("route_operation_id") == route_operation_id and row.get("step_code") == step_code:
                    return row
            return self.operation_step_row
        if "from mes.stations" in lowered and "station_code = %(station_code)s" in lowered:
            return {"station_exists": True} if self.station_exists else None
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
        if "from mes.items" in lowered:
            return self.item_rows
        if "from mes.process_routes" in lowered:
            return self.process_route_rows
        if "from mes.route_operations" in lowered:
            return self.route_operation_rows
        if "from mes.station_event_sources" in lowered:
            return self.station_event_source_rows
        if "from mes.operation_steps" in lowered:
            return self.operation_step_rows
        if "from mes.work_order_operation_steps" in lowered:
            operation_id = self.last_params.get("work_order_operation_id")
            return [
                row
                for row in sorted(self.execution_step_rows, key=lambda step: step.get("step_no", 0))
                if row.get("work_order_operation_id") == operation_id
            ]
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
                self.snapshot = deepcopy(connection.cursor_instance.__dict__)
                return self

            def __exit__(self, exc_type, *_args):
                if exc_type is not None:
                    connection.cursor_instance.__dict__.clear()
                    connection.cursor_instance.__dict__.update(self.snapshot)
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


def _unwrap_json_value(value):
    if value.__class__.__module__.startswith("psycopg.types.json") and hasattr(value, "obj"):
        return value.obj
    return value


def _assert_json_serializable_without_decimal(test_case: unittest.TestCase, value) -> None:
    value = _unwrap_json_value(value)
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
            payload = _unwrap_json_value(params.get("payload"))
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


def _fake_item(
    item_code: str,
    *,
    item_name: str | None = None,
    item_type: str = "raw_material",
    unit: str = "piece",
    active: bool = True,
    metadata: dict | None = None,
) -> dict:
    return {
        "item_code": item_code,
        "item_name": item_name or item_code.replace("_", " ").title(),
        "item_type": item_type,
        "unit": unit,
        "active": active,
        "metadata": metadata,
    }


def _fake_process_route(
    route_code: str = "ROUTE_BOX_PACKAGING_V1",
    *,
    version: int = 1,
    item_code: str = "PACKAGED_PRODUCT",
    active: bool = True,
    metadata: dict | None = None,
) -> dict:
    return {
        "route_code": route_code,
        "version": version,
        "route_name": "Box Packaging Demo Route V1",
        "item_code": item_code,
        "active": active,
        "metadata": metadata,
    }


def _fake_route_operation(
    route_operation_id: str = "ROUTE_BOX_PACKAGING_V1_OP10",
    *,
    route_code: str = "ROUTE_BOX_PACKAGING_V1",
    route_version: int = 1,
    sequence_no: int = 10,
    operation_code: str = "OP10_ASSEMBLY_CLASSIFICATION",
    operation_name: str = "Assembly / Classification",
    station_code: str = "ASSEMBLY_01",
    input_item_code: str = "RAW_BOX",
    output_item_code: str = "COLOR_CLASSIFIED_BOX",
    input_location_role: str = "input",
    output_location_role: str = "output_buffer",
    scrap_location_role: str | None = "output_scrap",
    operation_completion_policy: str = "auto_complete_pending_approval",
    active: bool = True,
    metadata: dict | None = None,
) -> dict:
    return {
        "route_operation_id": route_operation_id,
        "route_code": route_code,
        "route_version": route_version,
        "sequence_no": sequence_no,
        "operation_code": operation_code,
        "operation_name": operation_name,
        "station_code": station_code,
        "input_item_code": input_item_code,
        "output_item_code": output_item_code,
        "input_qty_per_cycle": Decimal("1.000000"),
        "output_qty_per_cycle": Decimal("1.000000"),
        "input_location_role": input_location_role,
        "output_location_role": output_location_role,
        "scrap_location_role": scrap_location_role,
        "operation_completion_policy": operation_completion_policy,
        "planned_cycle_time_sec": None,
        "active": active,
        "metadata": metadata,
    }


def _fake_station_event_source(
    station_code: str = "ASSEMBLY_01",
    source_code: str = "COLOR_SENSOR_ENTRY",
    *,
    source_type: str = "sensor",
    event_channel: str = "mqtt",
    mqtt_topic: str | None = "mes/stations/ASSEMBLY_01/sources/COLOR_SENSOR_ENTRY/events",
    active: bool = True,
    metadata: dict | None = None,
) -> dict:
    return {
        "station_code": station_code,
        "source_code": source_code,
        "source_name": source_code.replace("_", " ").title(),
        "source_type": source_type,
        "event_channel": event_channel,
        "mqtt_topic": mqtt_topic,
        "active": active,
        "metadata": metadata,
    }


def _fake_operation_step(
    route_operation_id: str = "ROUTE_BOX_PACKAGING_V1_OP10",
    step_code: str = "COLOR_SENSOR_ENTRY_EVIDENCE",
    *,
    operation_code: str = "OP10_ASSEMBLY_CLASSIFICATION",
    step_no: int = 10,
    start_mode: str = "auto_start",
    finish_mode: str = "auto_finish",
    start_event_source_code: str | None = "COLOR_SENSOR_ENTRY",
    finish_event_source_code: str | None = "COLOR_SENSOR_ENTRY",
    actor_type: str = "sensor",
    active: bool = True,
    metadata: dict | None = None,
) -> dict:
    return {
        "route_operation_id": route_operation_id,
        "operation_code": operation_code,
        "step_no": step_no,
        "step_code": step_code,
        "step_name": step_code.replace("_", " ").title(),
        "start_mode": start_mode,
        "finish_mode": finish_mode,
        "start_event_source_code": start_event_source_code,
        "finish_event_source_code": finish_event_source_code,
        "required_for_completion": True,
        "records_duration": False,
        "approval_required_after_finish": False,
        "actor_type": actor_type,
        "active": active,
        "metadata": metadata,
    }


def _fake_runtime_operation(
    work_order_operation_id: str = "11111111-1111-1111-1111-111111111111",
    *,
    order_id: str = "WO-E2E-MAVI-001",
    operation_code: str = "OP10_ASSEMBLY_CLASSIFICATION",
    station_code: str = "ASSEMBLY_01",
) -> dict:
    return {
        "work_order_operation_id": work_order_operation_id,
        "order_id": order_id,
        "operation_code": operation_code,
        "station_code": station_code,
    }


def _fake_execution_state(
    work_order_operation_id: str = "11111111-1111-1111-1111-111111111111",
    *,
    work_order_id: str = "WO-E2E-MAVI-001",
    station_code: str = "ASSEMBLY_01",
    operation_code: str = "OP10_ASSEMBLY_CLASSIFICATION",
    execution_status: str = "ready",
    operation_completion_policy: str = "auto_complete_pending_approval",
) -> dict:
    return {
        "execution_state_id": f"EXEC_STATE_{work_order_operation_id}",
        "work_order_operation_id": work_order_operation_id,
        "work_order_id": work_order_id,
        "station_code": station_code,
        "operation_code": operation_code,
        "execution_status": execution_status,
        "operation_completion_policy": operation_completion_policy,
        "current_step_code": None,
        "started_at": None,
        "evidence_completed_at": None,
        "pending_final_approval_at": None,
        "closed_at": None,
        "last_event_id": None,
        "last_approval_id": None,
        "created_at": datetime(2026, 7, 9, 10, 0, 0),
        "updated_at": datetime(2026, 7, 9, 10, 0, 0),
        "metadata": {"source": "runtime_engine_v0_phase1"},
    }


def _fake_execution_step(
    work_order_operation_id: str = "11111111-1111-1111-1111-111111111111",
    step_code: str = "COLOR_SENSOR_ENTRY_EVIDENCE",
    *,
    work_order_id: str = "WO-E2E-MAVI-001",
    operation_code: str = "OP10_ASSEMBLY_CLASSIFICATION",
    step_no: int = 10,
    station_code: str = "ASSEMBLY_01",
    status: str = "pending",
    required_for_completion: bool = True,
    approval_required_after_finish: bool = False,
) -> dict:
    return {
        "work_order_operation_step_id": f"EXEC_STEP_{work_order_operation_id}_{step_code}",
        "work_order_operation_id": work_order_operation_id,
        "work_order_id": work_order_id,
        "operation_code": operation_code,
        "step_code": step_code,
        "step_no": step_no,
        "station_code": station_code,
        "status": status,
        "started_at": None,
        "completed_at": None,
        "started_by_event_id": None,
        "completed_by_event_id": None,
        "required_for_completion": required_for_completion,
        "records_duration": False,
        "approval_required_after_finish": approval_required_after_finish,
        "created_at": datetime(2026, 7, 9, 10, 0, 0),
        "updated_at": datetime(2026, 7, 9, 10, 0, 0),
        "metadata": {"source": "runtime_engine_v0_phase1"},
    }


def _fake_operation_event(
    event_id: str = "OP_EVENT_ASSEMBLY_01_COLOR_SENSOR_ENTRY_sensor-001",
    *,
    work_order_operation_id: str = "11111111-1111-1111-1111-111111111111",
    station_code: str = "ASSEMBLY_01",
    event_source: str = "COLOR_SENSOR_ENTRY",
    event_type: str = "step_start",
    external_event_id: str | None = "sensor-001",
    idempotency_key: str = "ASSEMBLY_01:COLOR_SENSOR_ENTRY:sensor-001",
    payload: dict | None = None,
    accepted: bool = True,
    rejection_reason: str | None = None,
) -> dict:
    return {
        "event_id": event_id,
        "event_time": datetime(2026, 7, 9, 12, 0, 0),
        "received_at": datetime(2026, 7, 9, 12, 0, 1),
        "station_code": station_code,
        "work_order_id": None,
        "work_order_operation_id": work_order_operation_id,
        "work_order_operation_step_id": None,
        "operation_code": None,
        "step_code": None,
        "event_source": event_source,
        "event_type": event_type,
        "external_event_id": external_event_id,
        "idempotency_key": idempotency_key,
        "payload": payload or {},
        "accepted": accepted,
        "rejection_reason": rejection_reason,
        "created_at": datetime(2026, 7, 9, 12, 0, 1),
    }


def _seed_valid_route_operation_config(cursor: _Cursor) -> None:
    cursor.route_operation_rows = [_fake_route_operation()]
    cursor.item_rows = [
        _fake_item("RAW_BOX"),
        _fake_item("COLOR_CLASSIFIED_BOX", item_type="semi_finished"),
    ]
    cursor.station_event_source_rows = [
        _fake_station_event_source("ASSEMBLY_01", "COLOR_SENSOR_ENTRY")
    ]
    cursor.operation_step_rows = [
        _fake_operation_step(step_code="COLOR_SENSOR_ENTRY_EVIDENCE", step_no=10)
    ]
    cursor.runtime_operation_row = _fake_runtime_operation()


def _seed_startable_execution_step(
    cursor: _Cursor,
    *,
    execution_status: str = "ready",
    step_status: str = "pending",
    start_mode: str = "auto_start",
    event_source: str = "COLOR_SENSOR_ENTRY",
    configured_event_source: str | None = "COLOR_SENSOR_ENTRY",
    source_active: bool = True,
    state_station_code: str = "ASSEMBLY_01",
    step_station_code: str = "ASSEMBLY_01",
    route_operation_id: str | None = "ROUTE_BOX_PACKAGING_V1_OP10",
) -> None:
    state = _fake_execution_state(
        execution_status=execution_status,
        station_code=state_station_code,
    )
    state["metadata"] = {"route_operation_id": route_operation_id} if route_operation_id else {}
    if execution_status == "active":
        state["current_step_code"] = "COLOR_SENSOR_ENTRY_EVIDENCE"
        state["started_at"] = datetime(2026, 7, 9, 11, 0, 0)
    step = _fake_execution_step(
        station_code=step_station_code,
        status=step_status,
    )
    if step_status == "active":
        step["started_at"] = datetime(2026, 7, 9, 11, 0, 0)
        step["started_by_event_id"] = "OP_EVENT_FIRST_START"
    cursor.execution_state_row = state
    cursor.execution_step_rows = [step]
    cursor.operation_step_rows = [
        _fake_operation_step(
            start_mode=start_mode,
            start_event_source_code=configured_event_source,
        )
    ]
    cursor.station_event_source_rows = [
        _fake_station_event_source(
            state_station_code,
            event_source,
            active=source_active,
        )
    ]


def _seed_finishable_execution_step(
    cursor: _Cursor,
    *,
    execution_status: str = "active",
    step_status: str = "active",
    start_mode: str = "auto_start",
    finish_mode: str = "auto_finish",
    event_source: str = "COLOR_SENSOR_ENTRY",
    include_next_step: bool = True,
    operation_completion_policy: str = "auto_complete_pending_approval",
    required_for_completion: bool = True,
    approval_required_after_finish: bool = False,
) -> None:
    _seed_startable_execution_step(
        cursor,
        execution_status=execution_status,
        step_status=step_status,
        start_mode=start_mode,
        event_source=event_source,
        configured_event_source="COLOR_SENSOR_ENTRY",
    )
    cursor.operation_step_rows = [
        _fake_operation_step(
            start_mode=start_mode,
            finish_mode=finish_mode,
            finish_event_source_code=event_source,
        )
    ]
    cursor.execution_state_row["operation_completion_policy"] = operation_completion_policy
    cursor.execution_step_rows[0]["required_for_completion"] = required_for_completion
    cursor.execution_step_rows[0]["approval_required_after_finish"] = approval_required_after_finish
    cursor.operation_step_rows[0]["required_for_completion"] = required_for_completion
    cursor.operation_step_rows[0]["approval_required_after_finish"] = approval_required_after_finish
    if include_next_step:
        cursor.execution_step_rows.append(
            _fake_execution_step(
                step_code="ROBOT_ARM_DROP_COMPLETED",
                step_no=20,
                status="pending",
            )
        )


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

        self.assertIn("cast(%(location_type)s as text)", mesql_v2.SELECT_LOCATIONS_SQL.lower())
        self.assertIn("cast(%(role)s as text)", mesql_v2.SELECT_STATION_LOCATION_BINDINGS_SQL.lower())
        self.assertIn("cast(%(item_scope)s as text)", mesql_v2.SELECT_RESOLVE_STATION_LOCATION_SQL.lower())
        self.assertIn("cast(%(operation_scope)s as text)", mesql_v2.SELECT_RESOLVE_STATION_LOCATION_SQL.lower())

        for sql in (mesql_v2.SELECT_STATION_LOCATION_BINDINGS_SQL, mesql_v2.SELECT_RESOLVE_STATION_LOCATION_SQL):
            lowered = sql.lower()
            self.assertIn("from mes.station_location_bindings", lowered)
            self.assertIn("from mes.locations", lowered.replace("join", "from"))
            join_line = next(line.strip() for line in lowered.splitlines() if " on " in line.lower() or line.strip().startswith("on "))
            self.assertIn("l.location_code = b.location_code", join_line)
            self.assertNotIn("location_id", join_line)
            self.assertNotIn("location_pk", join_line)

    def test_list_items_reads_active_items_by_default(self) -> None:
        connection = _Connection()
        connection.cursor_instance.item_rows = [
            _fake_item("RAW_BOX", item_type="raw_material", metadata=None)
        ]

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            items = list_items(AppConfig(db_enabled=True))

        self.assertEqual(items[0]["item_code"], "RAW_BOX")
        self.assertEqual(items[0]["item_type"], "raw_material")
        self.assertEqual(items[0]["metadata"], {})
        self.assertEqual(connection.cursor_instance.last_params["active_only"], True)
        self.assertTrue(any("from mes.items" in sql.lower() for sql, _params in connection.cursor_instance.executed))

    def test_get_item_by_code_normalizes_code(self) -> None:
        connection = _Connection()
        connection.cursor_instance.item_rows = [_fake_item("RAW_BOX")]

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            item = get_item_by_code(AppConfig(db_enabled=True), " raw_box ")

        self.assertIsNotNone(item)
        self.assertEqual(item["item_code"], "RAW_BOX")
        self.assertEqual(connection.cursor_instance.last_params["item_code"], "RAW_BOX")

    def test_list_process_routes_filters_by_item_code(self) -> None:
        connection = _Connection()
        connection.cursor_instance.process_route_rows = [_fake_process_route()]

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            routes = list_process_routes(AppConfig(db_enabled=True), item_code="packaged_product")

        self.assertEqual(routes[0]["route_code"], "ROUTE_BOX_PACKAGING_V1")
        self.assertEqual(connection.cursor_instance.last_params["item_code"], "PACKAGED_PRODUCT")
        self.assertIn("cast(%(item_code)s as text)", connection.cursor_instance.last_sql.lower())

    def test_get_process_route_uses_route_code_and_version(self) -> None:
        connection = _Connection()
        connection.cursor_instance.process_route_rows = [_fake_process_route(version=1)]

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            route = get_process_route(AppConfig(db_enabled=True), "route_box_packaging_v1", version=1)

        self.assertIsNotNone(route)
        self.assertEqual(route["item_code"], "PACKAGED_PRODUCT")
        self.assertEqual(connection.cursor_instance.last_params["route_code"], "ROUTE_BOX_PACKAGING_V1")
        self.assertEqual(connection.cursor_instance.last_params["version"], 1)

    def test_list_route_operations_filters_by_station_code(self) -> None:
        connection = _Connection()
        connection.cursor_instance.route_operation_rows = [_fake_route_operation()]

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            operations = list_route_operations(AppConfig(db_enabled=True), station_code="assembly_01")

        self.assertEqual(operations[0]["station_code"], "ASSEMBLY_01")
        self.assertEqual(operations[0]["input_qty_per_cycle"], 1)
        self.assertEqual(connection.cursor_instance.last_params["station_code"], "ASSEMBLY_01")
        self.assertIn("order by route_code asc, route_version asc, sequence_no asc", connection.cursor_instance.last_sql.lower())

    def test_get_route_operation_missing_returns_none(self) -> None:
        connection = _Connection()

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            operation = get_route_operation(AppConfig(db_enabled=True), "missing")

        self.assertIsNone(operation)
        self.assertEqual(connection.cursor_instance.last_params["route_operation_id"], "MISSING")

    def test_list_station_event_sources_filters_by_station(self) -> None:
        connection = _Connection()
        connection.cursor_instance.station_event_source_rows = [
            _fake_station_event_source("ASSEMBLY_01", "COLOR_SENSOR_ENTRY")
        ]

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            sources = list_station_event_sources(AppConfig(db_enabled=True), "assembly_01")

        self.assertEqual(sources[0]["station_code"], "ASSEMBLY_01")
        self.assertEqual(sources[0]["source_type"], "sensor")
        self.assertEqual(connection.cursor_instance.last_params["station_code"], "ASSEMBLY_01")

    def test_resolve_station_event_source_normalizes_source(self) -> None:
        connection = _Connection()
        connection.cursor_instance.station_event_source_rows = [
            _fake_station_event_source("ASSEMBLY_01", "KIOSK_OPERATOR", source_type="kiosk", event_channel="kiosk", mqtt_topic=None)
        ]

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            source = resolve_station_event_source(AppConfig(db_enabled=True), "assembly_01", "kiosk_operator")

        self.assertIsNotNone(source)
        self.assertEqual(source["source_code"], "KIOSK_OPERATOR")
        self.assertEqual(connection.cursor_instance.last_params["source_code"], "KIOSK_OPERATOR")

    def test_list_operation_steps_orders_by_step_no(self) -> None:
        connection = _Connection()
        connection.cursor_instance.operation_step_rows = [
            _fake_operation_step(step_code="COLOR_SENSOR_ENTRY_EVIDENCE", step_no=10)
        ]

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            steps = list_operation_steps(AppConfig(db_enabled=True), "route_box_packaging_v1_op10")

        self.assertEqual(steps[0]["step_code"], "COLOR_SENSOR_ENTRY_EVIDENCE")
        self.assertEqual(connection.cursor_instance.last_params["route_operation_id"], "ROUTE_BOX_PACKAGING_V1_OP10")
        self.assertIn("order by step_no asc", connection.cursor_instance.last_sql.lower())

    def test_get_operation_step_missing_returns_none(self) -> None:
        connection = _Connection()

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            step = get_operation_step(AppConfig(db_enabled=True), "route_box_packaging_v1_op10", "missing")

        self.assertIsNone(step)
        self.assertEqual(connection.cursor_instance.last_params["step_code"], "MISSING")

    def test_get_route_operation_config_aggregate_includes_steps_items_and_sources(self) -> None:
        connection = _Connection()
        connection.cursor_instance.route_operation_rows = [_fake_route_operation()]
        connection.cursor_instance.item_rows = [
            _fake_item("RAW_BOX"),
            _fake_item("COLOR_CLASSIFIED_BOX", item_type="semi_finished"),
        ]
        connection.cursor_instance.station_event_source_rows = [
            _fake_station_event_source("ASSEMBLY_01", "COLOR_SENSOR_ENTRY")
        ]
        connection.cursor_instance.operation_step_rows = [
            _fake_operation_step(step_code="COLOR_SENSOR_ENTRY_EVIDENCE")
        ]

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            aggregate = get_route_operation_config(AppConfig(db_enabled=True), "route_box_packaging_v1_op10")

        self.assertIsNotNone(aggregate)
        self.assertEqual(aggregate["route_operation"]["station_code"], "ASSEMBLY_01")
        self.assertEqual(aggregate["input_item"]["item_code"], "RAW_BOX")
        self.assertEqual(aggregate["output_item"]["item_code"], "COLOR_CLASSIFIED_BOX")
        self.assertEqual(aggregate["steps"][0]["step_code"], "COLOR_SENSOR_ENTRY_EVIDENCE")
        self.assertEqual(aggregate["event_sources"][0]["source_code"], "COLOR_SENSOR_ENTRY")
        self.assertEqual(aggregate["validation"]["missing_event_sources"], [])

    def test_get_route_operation_config_reports_missing_event_source_ref(self) -> None:
        connection = _Connection()
        connection.cursor_instance.route_operation_rows = [_fake_route_operation()]
        connection.cursor_instance.item_rows = [
            _fake_item("RAW_BOX"),
            _fake_item("COLOR_CLASSIFIED_BOX", item_type="semi_finished"),
        ]
        connection.cursor_instance.station_event_source_rows = [
            _fake_station_event_source("ASSEMBLY_01", "COLOR_SENSOR_ENTRY")
        ]
        connection.cursor_instance.operation_step_rows = [
            _fake_operation_step(
                step_code="ROBOT_ARM_DROP_COMPLETED",
                step_no=20,
                start_mode="implicit_start",
                finish_mode="auto_finish",
                start_event_source_code=None,
                finish_event_source_code="ROBOT_ARM_DROP",
                actor_type="robot",
            )
        ]

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            aggregate = get_route_operation_config(AppConfig(db_enabled=True), "route_box_packaging_v1_op10")

        missing = aggregate["validation"]["missing_event_sources"]
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]["code"], "MISSING_EVENT_SOURCE")
        self.assertEqual(missing[0]["field"], "finish_event_source_code")
        self.assertEqual(missing[0]["source_code"], "ROBOT_ARM_DROP")

    def test_get_station_execution_config_includes_route_operations_for_station(self) -> None:
        connection = _Connection()
        connection.cursor_instance.route_operation_rows = [_fake_route_operation()]
        connection.cursor_instance.item_rows = [
            _fake_item("RAW_BOX"),
            _fake_item("COLOR_CLASSIFIED_BOX", item_type="semi_finished"),
        ]
        connection.cursor_instance.station_event_source_rows = [
            _fake_station_event_source("ASSEMBLY_01", "COLOR_SENSOR_ENTRY")
        ]
        connection.cursor_instance.operation_step_rows = [
            _fake_operation_step(step_code="COLOR_SENSOR_ENTRY_EVIDENCE")
        ]

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            config = get_station_execution_config(AppConfig(db_enabled=True), "assembly_01")

        self.assertEqual(config["station_code"], "ASSEMBLY_01")
        self.assertEqual(config["route_operations"][0]["route_operation"]["route_operation_id"], "ROUTE_BOX_PACKAGING_V1_OP10")
        self.assertEqual(config["event_sources"][0]["source_code"], "COLOR_SENSOR_ENTRY")

    def test_station_execution_config_helpers_are_read_only(self) -> None:
        read_sql_constants = [
            mesql_v2.SELECT_ITEMS_SQL,
            mesql_v2.SELECT_ITEM_BY_CODE_SQL,
            mesql_v2.SELECT_PROCESS_ROUTES_SQL,
            mesql_v2.SELECT_PROCESS_ROUTE_SQL,
            mesql_v2.SELECT_ROUTE_OPERATIONS_SQL,
            mesql_v2.SELECT_ROUTE_OPERATION_BY_ID_SQL,
            mesql_v2.SELECT_STATION_EVENT_SOURCES_SQL,
            mesql_v2.SELECT_STATION_EVENT_SOURCE_SQL,
            mesql_v2.SELECT_OPERATION_STEPS_SQL,
            mesql_v2.SELECT_OPERATION_STEP_SQL,
            mesql_v2.SELECT_STATION_EXISTS_SQL,
        ]
        forbidden_keywords = ("insert", "update", "delete", "drop", "truncate", "alter", "create")
        forbidden_tables = (
            "mes.work_order_operation_execution_state",
            "mes.work_order_operation_steps",
            "mes.operation_events",
            "mes.operation_approvals",
            "mes.production_flow_events",
            "mes.work_orders",
            "mes.work_order_operations",
            "mes.station_queue",
        )

        for sql in read_sql_constants:
            lowered = sql.lower()
            self.assertTrue(lowered.lstrip().startswith("select"))
            self.assertNotIn("for update", lowered)
            for keyword in forbidden_keywords:
                self.assertNotRegex(lowered, rf"\b{keyword}\b")
            for table_name in forbidden_tables:
                self.assertNotIn(table_name, lowered)

        self.assertIn("cast(%(active_only)s as boolean)", mesql_v2.SELECT_ITEMS_SQL.lower())
        self.assertIn("cast(%(item_code)s as text)", mesql_v2.SELECT_PROCESS_ROUTES_SQL.lower())
        self.assertIn("cast(%(route_code)s as text)", mesql_v2.SELECT_ROUTE_OPERATIONS_SQL.lower())
        self.assertIn("cast(%(station_code)s as text)", mesql_v2.SELECT_ROUTE_OPERATIONS_SQL.lower())

    def test_get_execution_state_returns_none_when_missing(self) -> None:
        connection = _Connection()

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            state = get_execution_state(AppConfig(db_enabled=True), "11111111-1111-1111-1111-111111111111")

        self.assertIsNone(state)
        self.assertEqual(connection.cursor_instance.last_params["work_order_operation_id"], "11111111-1111-1111-1111-111111111111")

    def test_list_execution_steps_orders_by_step_no(self) -> None:
        connection = _Connection()
        connection.cursor_instance.execution_step_rows = [
            _fake_execution_step(step_code="SECOND_STEP", step_no=20),
            _fake_execution_step(step_code="FIRST_STEP", step_no=10),
        ]

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            steps = list_execution_steps(AppConfig(db_enabled=True), "11111111-1111-1111-1111-111111111111")

        self.assertEqual([step["step_code"] for step in steps], ["FIRST_STEP", "SECOND_STEP"])
        self.assertIn("order by step_no asc", connection.cursor_instance.last_sql.lower())

    def test_initialize_execution_state_inserts_state_and_steps(self) -> None:
        connection = _Connection()
        _seed_valid_route_operation_config(connection.cursor_instance)

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            result = initialize_execution_state(
                AppConfig(db_enabled=True),
                work_order_operation_id="11111111-1111-1111-1111-111111111111",
                route_operation_id="route_box_packaging_v1_op10",
                station_code="assembly_01",
                actor_id="OP-001",
            )

        executed_sql = "\n".join(sql.lower() for sql, _params in connection.cursor_instance.executed)
        self.assertTrue(result["initialized"])
        self.assertEqual(result["execution_state"]["execution_status"], "ready")
        self.assertEqual(result["execution_state"]["operation_completion_policy"], "auto_complete_pending_approval")
        self.assertEqual(result["steps"][0]["step_code"], "COLOR_SENSOR_ENTRY_EVIDENCE")
        self.assertTrue(connection.transaction_entered)
        self.assertTrue(connection.committed)
        self.assertIn("insert into mes.work_order_operation_execution_state", executed_sql)
        self.assertIn("insert into mes.work_order_operation_steps", executed_sql)
        self.assertNotIn("insert into mes.operation_events", executed_sql)

    def test_initialize_execution_state_is_idempotent_when_state_exists(self) -> None:
        connection = _Connection()
        _seed_valid_route_operation_config(connection.cursor_instance)
        connection.cursor_instance.execution_state_row = _fake_execution_state()
        connection.cursor_instance.execution_step_rows = [
            _fake_execution_step(step_code="COLOR_SENSOR_ENTRY_EVIDENCE", step_no=10)
        ]

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            result = initialize_execution_state(
                AppConfig(db_enabled=True),
                work_order_operation_id="11111111-1111-1111-1111-111111111111",
                route_operation_id="ROUTE_BOX_PACKAGING_V1_OP10",
                station_code="ASSEMBLY_01",
            )

        executed_sql = "\n".join(sql.lower() for sql, _params in connection.cursor_instance.executed)
        self.assertFalse(result["initialized"])
        self.assertEqual(len(result["steps"]), 1)
        self.assertNotIn("insert into mes.work_order_operation_execution_state", executed_sql)
        self.assertNotIn("insert into mes.work_order_operation_steps", executed_sql)

    def test_initialize_execution_state_rejects_missing_identifiers(self) -> None:
        with self.assertRaises(mesql_v2.MesqlV2Error) as error:
            initialize_execution_state(
                AppConfig(db_enabled=True),
                work_order_operation_id="",
                route_operation_id="ROUTE_BOX_PACKAGING_V1_OP10",
                station_code="ASSEMBLY_01",
            )

        self.assertEqual(error.exception.detail, "RUNTIME_IDENTIFIER_REQUIRED")
        self.assertEqual(error.exception.status_code, 400)

    def test_initialize_execution_state_rejects_missing_route_operation_config(self) -> None:
        with patch.object(mesql_v2, "get_route_operation_config", return_value=None):
            with self.assertRaises(mesql_v2.MesqlV2Error) as error:
                initialize_execution_state(
                    AppConfig(db_enabled=True),
                    work_order_operation_id="11111111-1111-1111-1111-111111111111",
                    route_operation_id="MISSING_ROUTE_OPERATION",
                    station_code="ASSEMBLY_01",
                )

        self.assertEqual(error.exception.detail, "ROUTE_OPERATION_NOT_FOUND")
        self.assertEqual(error.exception.status_code, 404)

    def test_initialize_execution_state_rejects_invalid_config_validation(self) -> None:
        invalid_config = {
            "route_operation": _fake_route_operation(),
            "validation": {
                "missing_items": [{"code": "MISSING_INPUT_ITEM"}],
                "missing_station": [],
                "missing_event_sources": [],
                "invalid_step_source_refs": [],
                "invalid_auto_mode_refs": [],
            },
        }

        with patch.object(mesql_v2, "get_route_operation_config", return_value=invalid_config):
            with self.assertRaises(mesql_v2.MesqlV2Error) as error:
                initialize_execution_state(
                    AppConfig(db_enabled=True),
                    work_order_operation_id="11111111-1111-1111-1111-111111111111",
                    route_operation_id="ROUTE_BOX_PACKAGING_V1_OP10",
                    station_code="ASSEMBLY_01",
                )

        self.assertEqual(error.exception.detail, "ROUTE_OPERATION_CONFIG_INVALID")
        self.assertEqual(error.exception.status_code, 409)

    def test_runtime_initialize_does_not_write_forbidden_tables(self) -> None:
        write_sql_constants = [
            mesql_v2.INSERT_EXECUTION_STATE_SQL,
            mesql_v2.INSERT_EXECUTION_STEP_SQL,
        ]
        allowed_write_tables = (
            "mes.work_order_operation_execution_state",
            "mes.work_order_operation_steps",
        )
        forbidden_write_tables = (
            "mes.work_orders",
            "mes.work_order_operations",
            "mes.station_queue",
            "mes.items",
            "mes.process_routes",
            "mes.route_operations",
            "mes.operation_steps",
            "mes.station_event_sources",
            "mes.locations",
            "mes.station_location_bindings",
            "mes.operation_events",
            "mes.operation_approvals",
            "mes.production_flow_events",
        )

        for sql in write_sql_constants:
            lowered = sql.lower()
            self.assertTrue(lowered.lstrip().startswith("insert"))
            self.assertTrue(any(table_name in lowered for table_name in allowed_write_tables))
            for table_name in forbidden_write_tables:
                self.assertNotRegex(lowered, rf"\b(insert\s+into|update|delete\s+from)\s+{table_name}\b")

    def _start_step(self, connection: _Connection, **values):
        defaults = {
            "work_order_operation_id": "11111111-1111-1111-1111-111111111111",
            "step_code": "color_sensor_entry_evidence",
            "event_source": "color_sensor_entry",
            "external_event_id": "start-event-001",
        }
        defaults.update(values)

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            return start_execution_step(AppConfig(db_enabled=True), **defaults)

    def test_start_execution_step_transitions_ready_pending_and_records_context(self) -> None:
        connection = _Connection()
        _seed_startable_execution_step(connection.cursor_instance)

        result = self._start_step(connection, actor_id="OP-001", payload={"source": "unit"})

        self.assertTrue(result["started"])
        self.assertTrue(result["event_inserted"])
        self.assertEqual(result["execution_state"]["execution_status"], "active")
        self.assertEqual(result["execution_state"]["current_step_code"], "COLOR_SENSOR_ENTRY_EVIDENCE")
        self.assertEqual(result["step"]["status"], "active")
        self.assertEqual(result["event"]["event_type"], "step_start")
        self.assertEqual(result["event"]["work_order_id"], "WO-E2E-MAVI-001")
        self.assertEqual(result["event"]["operation_code"], "OP10_ASSEMBLY_CLASSIFICATION")
        self.assertEqual(result["event"]["work_order_operation_step_id"], result["step"]["work_order_operation_step_id"])
        self.assertEqual(result["event"]["payload"]["action"], "start")
        self.assertEqual(result["event"]["payload"]["actor_id"], "OP-001")
        self.assertEqual(result["step"]["started_by_event_id"], result["event"]["event_id"])
        self.assertEqual(result["execution_state"]["last_event_id"], result["event"]["event_id"])
        self.assertTrue(connection.transaction_entered)
        self.assertTrue(connection.committed)

    def test_start_execution_step_transitions_active_pending(self) -> None:
        connection = _Connection()
        _seed_startable_execution_step(connection.cursor_instance, execution_status="active")

        result = self._start_step(connection, external_event_id="start-event-active-pending")

        self.assertTrue(result["started"])
        self.assertEqual(result["execution_state"]["execution_status"], "active")
        self.assertEqual(result["step"]["status"], "active")

    def test_start_execution_step_derives_external_event_idempotency_key(self) -> None:
        connection = _Connection()
        _seed_startable_execution_step(connection.cursor_instance)

        result = self._start_step(connection)

        self.assertEqual(result["event"]["idempotency_key"], "ASSEMBLY_01:COLOR_SENSOR_ENTRY:start-event-001")

    def test_start_execution_step_idempotency_key_replay_skips_all_state_mutation(self) -> None:
        connection = _Connection()
        _seed_startable_execution_step(connection.cursor_instance)
        existing = _fake_operation_event(idempotency_key="start-key-001", external_event_id=None)
        connection.cursor_instance.operation_event_rows = [existing]

        result = self._start_step(connection, idempotency_key="start-key-001", external_event_id=None)

        sql = "\n".join(sql.lower() for sql, _params in connection.cursor_instance.executed)
        self.assertFalse(result["started"])
        self.assertFalse(result["event_inserted"])
        self.assertEqual(result["event"]["event_id"], existing["event_id"])
        self.assertNotIn("insert into mes.operation_events", sql)
        self.assertNotIn("update mes.work_order_operation_execution_state", sql)
        self.assertNotIn("update mes.work_order_operation_steps", sql)

    def test_start_execution_step_external_event_replay_skips_all_state_mutation(self) -> None:
        connection = _Connection()
        _seed_startable_execution_step(connection.cursor_instance)
        existing = _fake_operation_event(external_event_id="start-event-001")
        connection.cursor_instance.operation_event_rows = [existing]

        result = self._start_step(connection, idempotency_key="another-key")

        sql = "\n".join(sql.lower() for sql, _params in connection.cursor_instance.executed)
        self.assertFalse(result["started"])
        self.assertFalse(result["event_inserted"])
        self.assertNotIn("insert into mes.operation_events", sql)
        self.assertNotIn("update mes.work_order_operation_execution_state", sql)
        self.assertNotIn("update mes.work_order_operation_steps", sql)

    def test_start_execution_step_duplicate_preserves_first_start_references(self) -> None:
        connection = _Connection()
        _seed_startable_execution_step(connection.cursor_instance, execution_status="active", step_status="active")
        before_state = dict(connection.cursor_instance.execution_state_row)
        before_step = dict(connection.cursor_instance.execution_step_rows[0])
        connection.cursor_instance.operation_event_rows = [_fake_operation_event(external_event_id="start-event-001")]

        self._start_step(connection)

        self.assertEqual(connection.cursor_instance.execution_state_row["started_at"], before_state["started_at"])
        self.assertEqual(connection.cursor_instance.execution_state_row["last_event_id"], before_state["last_event_id"])
        self.assertEqual(connection.cursor_instance.execution_step_rows[0]["started_at"], before_step["started_at"])
        self.assertEqual(connection.cursor_instance.execution_step_rows[0]["started_by_event_id"], before_step["started_by_event_id"])

    def test_start_execution_step_active_step_accepts_new_event_without_restarting(self) -> None:
        connection = _Connection()
        _seed_startable_execution_step(connection.cursor_instance, execution_status="active", step_status="active")
        before_step = dict(connection.cursor_instance.execution_step_rows[0])

        result = self._start_step(connection, external_event_id="new-active-event")

        sql = "\n".join(sql.lower() for sql, _params in connection.cursor_instance.executed)
        self.assertFalse(result["started"])
        self.assertTrue(result["event_inserted"])
        self.assertEqual(result["step"]["started_at"], before_step["started_at"].isoformat())
        self.assertEqual(result["step"]["started_by_event_id"], before_step["started_by_event_id"])
        self.assertNotIn("update mes.work_order_operation_execution_state", sql)
        self.assertNotIn("update mes.work_order_operation_steps", sql)

    def test_start_execution_step_rejects_missing_identifiers(self) -> None:
        for values in (
            {"work_order_operation_id": ""},
            {"step_code": ""},
            {"event_source": ""},
        ):
            with self.subTest(values=values):
                with self.assertRaises(mesql_v2.MesqlV2Error) as error:
                    self._start_step(_Connection(), **values)
                self.assertEqual(error.exception.detail, "RUNTIME_STEP_IDENTIFIER_REQUIRED")
                self.assertEqual(error.exception.status_code, 400)

    def test_start_execution_step_rejects_missing_idempotency(self) -> None:
        connection = _Connection()
        _seed_startable_execution_step(connection.cursor_instance)

        with self.assertRaises(mesql_v2.MesqlV2Error) as error:
            self._start_step(connection, external_event_id=None, idempotency_key=None)

        self.assertEqual(error.exception.detail, "OPERATION_EVENT_IDEMPOTENCY_REQUIRED")
        self.assertEqual(error.exception.status_code, 400)

    def test_start_execution_step_rejects_missing_execution_state_or_step(self) -> None:
        connection = _Connection()
        with self.assertRaises(mesql_v2.MesqlV2Error) as error:
            self._start_step(connection)
        self.assertEqual(error.exception.detail, "EXECUTION_STATE_NOT_FOUND")

        connection = _Connection()
        _seed_startable_execution_step(connection.cursor_instance)
        connection.cursor_instance.execution_step_rows = []
        with self.assertRaises(mesql_v2.MesqlV2Error) as error:
            self._start_step(connection)
        self.assertEqual(error.exception.detail, "EXECUTION_STEP_NOT_FOUND")

    def test_start_execution_step_rejects_missing_route_context_or_step_config(self) -> None:
        connection = _Connection()
        _seed_startable_execution_step(connection.cursor_instance, route_operation_id=None)
        with self.assertRaises(mesql_v2.MesqlV2Error) as error:
            self._start_step(connection)
        self.assertEqual(error.exception.detail, "RUNTIME_ROUTE_OPERATION_CONTEXT_MISSING")

        connection = _Connection()
        _seed_startable_execution_step(connection.cursor_instance)
        connection.cursor_instance.operation_step_rows = []
        with self.assertRaises(mesql_v2.MesqlV2Error) as error:
            self._start_step(connection)
        self.assertEqual(error.exception.detail, "OPERATION_STEP_CONFIG_NOT_FOUND")

    def test_start_execution_step_rejects_missing_or_inactive_station_event_source(self) -> None:
        for active, source_rows in ((False, None), (True, [])):
            with self.subTest(active=active, source_rows=source_rows):
                connection = _Connection()
                _seed_startable_execution_step(connection.cursor_instance, source_active=active)
                if source_rows == []:
                    connection.cursor_instance.station_event_source_rows = []
                with self.assertRaises(mesql_v2.MesqlV2Error) as error:
                    self._start_step(connection)
                self.assertEqual(error.exception.detail, "STATION_EVENT_SOURCE_NOT_FOUND")
                self.assertEqual(error.exception.status_code, 404)

    def test_start_execution_step_rejects_source_mismatch_and_unsupported_modes(self) -> None:
        connection = _Connection()
        _seed_startable_execution_step(connection.cursor_instance, configured_event_source="KIOSK_OPERATOR")
        with self.assertRaises(mesql_v2.MesqlV2Error) as error:
            self._start_step(connection)
        self.assertEqual(error.exception.detail, "STEP_START_EVENT_SOURCE_MISMATCH")

        for start_mode in ("none", "implicit_start"):
            with self.subTest(start_mode=start_mode):
                connection = _Connection()
                _seed_startable_execution_step(connection.cursor_instance, start_mode=start_mode, configured_event_source=None)
                with self.assertRaises(mesql_v2.MesqlV2Error) as error:
                    self._start_step(connection)
                self.assertEqual(error.exception.detail, "STEP_START_MODE_NOT_SUPPORTED")
                self.assertEqual(error.exception.status_code, 409)

    def test_start_execution_step_rejects_forbidden_execution_and_step_states(self) -> None:
        for status in ("queued", "evidence_completed", "pending_final_approval", "closed", "cancelled", "failed"):
            with self.subTest(execution_status=status):
                connection = _Connection()
                _seed_startable_execution_step(connection.cursor_instance, execution_status=status)
                with self.assertRaises(mesql_v2.MesqlV2Error) as error:
                    self._start_step(connection)
                self.assertEqual(error.exception.detail, "EXECUTION_STATE_NOT_STARTABLE")

        for status in ("completed", "skipped", "failed", "cancelled"):
            with self.subTest(step_status=status):
                connection = _Connection()
                _seed_startable_execution_step(connection.cursor_instance, step_status=status)
                with self.assertRaises(mesql_v2.MesqlV2Error) as error:
                    self._start_step(connection)
                self.assertEqual(error.exception.detail, "EXECUTION_STEP_NOT_STARTABLE")

    def test_start_execution_step_rejects_runtime_station_mismatch(self) -> None:
        connection = _Connection()
        _seed_startable_execution_step(connection.cursor_instance, step_station_code="PACKAGING_01")

        with self.assertRaises(mesql_v2.MesqlV2Error) as error:
            self._start_step(connection)

        self.assertEqual(error.exception.detail, "RUNTIME_STATION_MISMATCH")
        self.assertEqual(error.exception.status_code, 409)

    def test_start_execution_step_does_not_commit_when_state_or_step_update_fails(self) -> None:
        for fragment in (
            "update mes.work_order_operation_execution_state",
            "update mes.work_order_operation_steps",
        ):
            with self.subTest(fragment=fragment):
                connection = _Connection()
                _seed_startable_execution_step(connection.cursor_instance)
                connection.cursor_instance.raise_on_sql_fragment = fragment
                with self.assertRaises(RuntimeError):
                    self._start_step(connection)
                self.assertFalse(connection.committed)

    def test_start_execution_phase_writes_only_event_and_runtime_sidecar_tables(self) -> None:
        write_sql_constants = (
            mesql_v2.INSERT_OPERATION_EVENT_SQL,
            mesql_v2.UPDATE_EXECUTION_STATE_STEP_STARTED_SQL,
            mesql_v2.UPDATE_EXECUTION_STEP_STARTED_SQL,
        )
        forbidden_tables = (
            "mes.work_orders",
            "mes.work_order_operations",
            "mes.station_queue",
            "mes.operation_approvals",
            "mes.production_flow_events",
            "mes.items",
            "mes.process_routes",
            "mes.route_operations",
            "mes.operation_steps",
            "mes.station_event_sources",
            "mes.locations",
            "mes.station_location_bindings",
        )
        for sql in write_sql_constants:
            lowered = sql.lower()
            self.assertTrue(lowered.lstrip().startswith(("insert", "update")))
            for table_name in forbidden_tables:
                self.assertNotRegex(lowered, rf"\\b(insert\\s+into|update|delete\\s+from)\\s+{table_name}\\b")

    def _finish_step(self, connection: _Connection, **values):
        defaults = {
            "work_order_operation_id": "11111111-1111-1111-1111-111111111111",
            "step_code": "COLOR_SENSOR_ENTRY_EVIDENCE",
            "event_source": "COLOR_SENSOR_ENTRY",
            "external_event_id": "finish-event-001",
        }
        defaults.update(values)

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            return finish_execution_step(AppConfig(db_enabled=True), **defaults)

    def test_completion_policy_resolver_and_required_step_predicate(self) -> None:
        completed_required = _fake_execution_step(status="completed")
        optional_pending = _fake_execution_step(
            step_code="OPTIONAL_NOTE",
            step_no=20,
            status="pending",
            required_for_completion=False,
        )
        self.assertTrue(mesql_v2._required_steps_completed([completed_required, optional_pending]))
        self.assertFalse(mesql_v2._required_steps_completed([optional_pending]))

        for blocking_status in ("pending", "active", "failed", "cancelled", "skipped"):
            with self.subTest(blocking_status=blocking_status):
                blocking = _fake_execution_step(
                    step_code="BLOCKING_STEP",
                    step_no=20,
                    status=blocking_status,
                )
                self.assertFalse(
                    mesql_v2._required_steps_completed([completed_required, blocking])
                )

        expected = {
            "manual_close": ("evidence_completed", False, False),
            "auto_close_on_required_steps": ("closed", False, True),
            "auto_complete_pending_approval": ("pending_final_approval", True, False),
        }
        for policy, values in expected.items():
            with self.subTest(policy=policy):
                transition = mesql_v2._resolve_completion_policy_transition(
                    operation_completion_policy=policy,
                    required_steps_completed=True,
                )
                self.assertTrue(transition["policy_applied"])
                self.assertEqual(
                    (
                        transition["execution_status"],
                        transition["set_pending_final_approval_at"],
                        transition["set_closed_at"],
                    ),
                    values,
                )

        inactive = mesql_v2._resolve_completion_policy_transition(
            operation_completion_policy="unsupported_until_required_complete",
            required_steps_completed=False,
        )
        self.assertFalse(inactive["policy_applied"])
        with self.assertRaises(mesql_v2.MesqlV2Error) as error:
            mesql_v2._resolve_completion_policy_transition(
                operation_completion_policy="unsupported",
                required_steps_completed=True,
            )
        self.assertEqual(error.exception.detail, "OPERATION_COMPLETION_POLICY_UNSUPPORTED")

    def test_finish_execution_step_completes_active_auto_and_manual_steps(self) -> None:
        for finish_mode, event_source in (("auto_finish", "COLOR_SENSOR_ENTRY"), ("manual_finish", "KIOSK_OPERATOR")):
            with self.subTest(finish_mode=finish_mode):
                connection = _Connection()
                _seed_finishable_execution_step(connection.cursor_instance, finish_mode=finish_mode, event_source=event_source)
                before_step = dict(connection.cursor_instance.execution_step_rows[0])
                result = self._finish_step(connection, event_source=event_source)
                self.assertTrue(result["finished"])
                self.assertTrue(result["event_inserted"])
                self.assertFalse(result["implicit_started"])
                self.assertEqual(result["event"]["event_type"], "step_finish")
                self.assertEqual(result["step"]["status"], "completed")
                self.assertEqual(result["step"]["started_at"], before_step["started_at"].isoformat())
                self.assertEqual(result["step"]["started_by_event_id"], before_step["started_by_event_id"])
                self.assertEqual(result["step"]["completed_by_event_id"], result["event"]["event_id"])
                self.assertEqual(result["execution_state"]["execution_status"], "active")
                self.assertEqual(result["execution_state"]["current_step_code"], "ROBOT_ARM_DROP_COMPLETED")
                self.assertEqual(result["next_step"]["status"], "pending")
                self.assertFalse(result["completion_policy_applied"])
                self.assertFalse(result["required_steps_completed"])
                self.assertIsNone(result["execution_transition"])

    def test_finish_execution_step_implicitly_starts_supported_pending_combinations(self) -> None:
        for start_mode, finish_mode in (("auto_start", "auto_finish"), ("implicit_start", "auto_finish"), ("implicit_start", "manual_finish")):
            with self.subTest(start_mode=start_mode, finish_mode=finish_mode):
                connection = _Connection()
                _seed_finishable_execution_step(connection.cursor_instance, step_status="pending", start_mode=start_mode, finish_mode=finish_mode)
                result = self._finish_step(connection, external_event_id=f"finish-{start_mode}-{finish_mode}")
                self.assertTrue(result["finished"])
                self.assertTrue(result["implicit_started"])
                self.assertEqual(result["step"]["status"], "completed")
                self.assertEqual(result["step"]["started_by_event_id"], result["event"]["event_id"])
                self.assertEqual(result["step"]["completed_by_event_id"], result["event"]["event_id"])

    def test_finish_execution_step_rejects_pending_manual_start_and_allows_ready_implicit(self) -> None:
        connection = _Connection()
        _seed_finishable_execution_step(connection.cursor_instance, step_status="pending", start_mode="manual_start", finish_mode="manual_finish")
        with self.assertRaises(mesql_v2.MesqlV2Error) as error:
            self._finish_step(connection)
        self.assertEqual(error.exception.detail, "STEP_START_REQUIRED")

        connection = _Connection()
        _seed_finishable_execution_step(connection.cursor_instance, execution_status="ready", step_status="pending")
        result = self._finish_step(connection)
        self.assertTrue(result["implicit_started"])
        self.assertEqual(result["execution_state"]["execution_status"], "active")

    def test_finish_execution_step_advances_current_step_and_applies_final_policy(self) -> None:
        connection = _Connection()
        _seed_finishable_execution_step(connection.cursor_instance)
        result = self._finish_step(connection)
        self.assertEqual(result["execution_state"]["current_step_code"], "ROBOT_ARM_DROP_COMPLETED")
        self.assertEqual(result["next_step"]["status"], "pending")
        self.assertFalse(result["completion_policy_applied"])

        connection = _Connection()
        _seed_finishable_execution_step(connection.cursor_instance, include_next_step=False)
        result = self._finish_step(connection)
        self.assertIsNone(result["next_step"])
        self.assertIsNone(result["execution_state"]["current_step_code"])
        self.assertEqual(result["execution_state"]["execution_status"], "pending_final_approval")
        self.assertEqual(
            result["execution_state"]["evidence_completed_at"],
            result["event"]["event_time"],
        )
        self.assertEqual(
            result["execution_state"]["pending_final_approval_at"],
            result["event"]["event_time"],
        )
        self.assertIsNone(result["execution_state"]["closed_at"])
        self.assertTrue(result["completion_policy_applied"])
        self.assertTrue(result["required_steps_completed"])

    def test_finish_execution_step_applies_final_completion_policies(self) -> None:
        cases = {
            "manual_close": ("evidence_completed", False, False),
            "auto_close_on_required_steps": ("closed", False, True),
            "auto_complete_pending_approval": ("pending_final_approval", True, False),
        }
        for policy, (expected_status, expect_pending, expect_closed) in cases.items():
            with self.subTest(policy=policy):
                connection = _Connection()
                _seed_finishable_execution_step(
                    connection.cursor_instance,
                    include_next_step=False,
                    operation_completion_policy=policy,
                )
                started_at = datetime(2026, 7, 9, 11, 0, 0)
                connection.cursor_instance.execution_state_row["started_at"] = started_at
                connection.cursor_instance.execution_state_row["last_approval_id"] = "APPROVAL-KEPT"
                result = self._finish_step(
                    connection,
                    external_event_id=f"finish-{policy}",
                )
                event_time = result["event"]["event_time"]
                state = result["execution_state"]
                self.assertEqual(state["execution_status"], expected_status)
                self.assertIsNone(state["current_step_code"])
                self.assertEqual(state["evidence_completed_at"], event_time)
                self.assertEqual(
                    state["pending_final_approval_at"],
                    event_time if expect_pending else None,
                )
                self.assertEqual(state["closed_at"], event_time if expect_closed else None)
                self.assertEqual(state["last_event_id"], result["event"]["event_id"])
                self.assertEqual(state["updated_at"], event_time)
                self.assertEqual(state["started_at"], started_at.isoformat())
                self.assertEqual(state["last_approval_id"], "APPROVAL-KEPT")
                self.assertTrue(result["completion_policy_applied"])
                self.assertEqual(result["completion_policy"], policy)
                self.assertEqual(
                    result["execution_transition"],
                    {"from_status": "active", "to_status": expected_status},
                )
                self.assertEqual(len(connection.cursor_instance.operation_event_rows), 1)

    def test_finish_execution_step_optional_pending_does_not_block_policy(self) -> None:
        connection = _Connection()
        _seed_finishable_execution_step(
            connection.cursor_instance,
            include_next_step=False,
            operation_completion_policy="auto_close_on_required_steps",
        )
        optional_step = _fake_execution_step(
            step_code="OPTIONAL_NOTE",
            step_no=20,
            status="pending",
            required_for_completion=False,
        )
        connection.cursor_instance.execution_step_rows.append(optional_step)
        result = self._finish_step(connection)
        self.assertEqual(result["execution_state"]["execution_status"], "closed")
        self.assertIsNone(result["execution_state"]["current_step_code"])
        self.assertIsNone(result["next_step"])
        self.assertEqual(connection.cursor_instance.execution_step_rows[1]["status"], "pending")

    def test_finish_execution_step_operation_policy_overrides_step_approval_metadata(self) -> None:
        connection = _Connection()
        _seed_finishable_execution_step(
            connection.cursor_instance,
            include_next_step=False,
            operation_completion_policy="auto_close_on_required_steps",
            approval_required_after_finish=True,
        )
        result = self._finish_step(connection)
        self.assertTrue(result["step"]["approval_required_after_finish"])
        self.assertEqual(result["execution_state"]["execution_status"], "closed")
        self.assertIsNone(result["execution_state"]["pending_final_approval_at"])

    def test_finish_execution_step_required_blockers_and_no_required_steps_skip_policy(self) -> None:
        for blocking_status in ("pending", "active", "failed", "cancelled", "skipped"):
            with self.subTest(blocking_status=blocking_status):
                connection = _Connection()
                _seed_finishable_execution_step(
                    connection.cursor_instance,
                    include_next_step=False,
                    operation_completion_policy="auto_close_on_required_steps",
                )
                connection.cursor_instance.execution_step_rows.append(
                    _fake_execution_step(
                        step_code="BLOCKING_STEP",
                        step_no=20,
                        status=blocking_status,
                    )
                )
                result = self._finish_step(
                    connection,
                    external_event_id=f"finish-blocked-{blocking_status}",
                )
                self.assertFalse(result["required_steps_completed"])
                self.assertFalse(result["completion_policy_applied"])
                self.assertEqual(result["execution_state"]["execution_status"], "active")

        connection = _Connection()
        _seed_finishable_execution_step(
            connection.cursor_instance,
            include_next_step=False,
            operation_completion_policy="auto_close_on_required_steps",
            required_for_completion=False,
        )
        result = self._finish_step(connection, external_event_id="finish-no-required")
        self.assertFalse(result["required_steps_completed"])
        self.assertFalse(result["completion_policy_applied"])
        self.assertEqual(result["execution_state"]["execution_status"], "active")

    def test_finish_execution_step_duplicate_precedes_completed_validation(self) -> None:
        connection = _Connection()
        _seed_finishable_execution_step(connection.cursor_instance, step_status="completed")
        connection.cursor_instance.operation_event_rows = [_fake_operation_event(event_type="step_finish", external_event_id="finish-event-001")]
        before_state = deepcopy(connection.cursor_instance.execution_state_row)
        before_steps = deepcopy(connection.cursor_instance.execution_step_rows)
        result = self._finish_step(connection)
        sql = "\n".join(sql.lower() for sql, _params in connection.cursor_instance.executed)
        self.assertFalse(result["finished"])
        self.assertFalse(result["event_inserted"])
        self.assertFalse(result["implicit_started"])
        self.assertFalse(result["completion_policy_applied"])
        self.assertIsNone(result["execution_transition"])
        self.assertEqual(connection.cursor_instance.execution_state_row, before_state)
        self.assertEqual(connection.cursor_instance.execution_step_rows, before_steps)
        self.assertNotIn("insert into mes.operation_events", sql)
        self.assertNotIn("update mes.work_order_operation_steps", sql)
        self.assertNotIn("update mes.work_order_operation_execution_state", sql)

        connection = _Connection()
        _seed_finishable_execution_step(connection.cursor_instance)
        connection.cursor_instance.operation_event_rows = [_fake_operation_event(event_type="step_finish", idempotency_key="finish-key-001", external_event_id=None)]
        result = self._finish_step(connection, idempotency_key="finish-key-001", external_event_id=None)
        self.assertFalse(result["finished"])
        self.assertFalse(result["event_inserted"])
        self.assertFalse(result["completion_policy_applied"])

    def test_finish_execution_step_rejects_terminal_statuses_and_validation_errors(self) -> None:
        for step_status, expected in (("completed", "STEP_ALREADY_COMPLETED"), ("skipped", "STEP_STATUS_NOT_FINISHABLE"), ("failed", "STEP_STATUS_NOT_FINISHABLE"), ("cancelled", "STEP_STATUS_NOT_FINISHABLE")):
            with self.subTest(step_status=step_status):
                connection = _Connection()
                _seed_finishable_execution_step(connection.cursor_instance, step_status=step_status)
                with self.assertRaises(mesql_v2.MesqlV2Error) as error:
                    self._finish_step(connection)
                self.assertEqual(error.exception.detail, expected)
        for execution_status in ("queued", "evidence_completed", "pending_final_approval", "closed", "cancelled", "failed"):
            with self.subTest(execution_status=execution_status):
                connection = _Connection()
                _seed_finishable_execution_step(connection.cursor_instance, execution_status=execution_status)
                with self.assertRaises(mesql_v2.MesqlV2Error) as error:
                    self._finish_step(connection)
                self.assertEqual(error.exception.detail, "EXECUTION_STATUS_NOT_FINISHABLE")

    def test_finish_execution_step_validates_modes_source_actionability_and_inputs(self) -> None:
        connection = _Connection()
        _seed_finishable_execution_step(connection.cursor_instance, finish_mode="implicit_finish")
        with self.assertRaises(mesql_v2.MesqlV2Error) as error:
            self._finish_step(connection)
        self.assertEqual(error.exception.detail, "STEP_FINISH_MODE_UNSUPPORTED")

        connection = _Connection()
        _seed_finishable_execution_step(connection.cursor_instance)
        connection.cursor_instance.station_event_source_rows = [_fake_station_event_source("ASSEMBLY_01", "KIOSK_OPERATOR")]
        with self.assertRaises(mesql_v2.MesqlV2Error) as error:
            self._finish_step(connection, event_source="KIOSK_OPERATOR")
        self.assertEqual(error.exception.detail, "STEP_FINISH_SOURCE_MISMATCH")

        for source_rows in ([], [_fake_station_event_source("ASSEMBLY_01", "COLOR_SENSOR_ENTRY", active=False)]):
            connection = _Connection()
            _seed_finishable_execution_step(connection.cursor_instance)
            connection.cursor_instance.station_event_source_rows = source_rows
            with self.assertRaises(mesql_v2.MesqlV2Error) as error:
                self._finish_step(connection)
            self.assertEqual(error.exception.detail, "STATION_EVENT_SOURCE_NOT_FOUND")

        connection = _Connection()
        _seed_finishable_execution_step(connection.cursor_instance)
        connection.cursor_instance.execution_step_rows[0]["status"] = "pending"
        connection.cursor_instance.operation_step_rows.append(
            _fake_operation_step(
                step_code="ROBOT_ARM_DROP_COMPLETED",
                step_no=20,
                finish_event_source_code="ROBOT_ARM_DROP",
            )
        )
        connection.cursor_instance.station_event_source_rows.append(
            _fake_station_event_source("ASSEMBLY_01", "ROBOT_ARM_DROP")
        )
        with self.assertRaises(mesql_v2.MesqlV2Error) as error:
            self._finish_step(
                connection,
                step_code="ROBOT_ARM_DROP_COMPLETED",
                event_source="ROBOT_ARM_DROP",
            )
        self.assertEqual(error.exception.detail, "STEP_NOT_ACTIONABLE")

        for values in ({"work_order_operation_id": ""}, {"step_code": ""}, {"event_source": ""}, {"external_event_id": None, "idempotency_key": None}):
            with self.subTest(values=values):
                with self.assertRaises(mesql_v2.MesqlV2Error):
                    self._finish_step(_Connection(), **values)

        connection = _Connection()
        with self.assertRaises(mesql_v2.MesqlV2Error) as error:
            self._finish_step(connection)
        self.assertEqual(error.exception.detail, "EXECUTION_STATE_NOT_FOUND")

        connection = _Connection()
        _seed_finishable_execution_step(connection.cursor_instance)
        connection.cursor_instance.execution_step_rows = []
        with self.assertRaises(mesql_v2.MesqlV2Error) as error:
            self._finish_step(connection)
        self.assertEqual(error.exception.detail, "EXECUTION_STEP_NOT_FOUND")

        connection = _Connection()
        _seed_finishable_execution_step(connection.cursor_instance)
        connection.cursor_instance.operation_step_rows = []
        with self.assertRaises(mesql_v2.MesqlV2Error) as error:
            self._finish_step(connection)
        self.assertEqual(error.exception.detail, "OPERATION_STEP_CONFIG_NOT_FOUND")

    def test_finish_execution_step_records_json_safe_context_and_rolls_back(self) -> None:
        connection = _Connection()
        _seed_finishable_execution_step(connection.cursor_instance)
        result = self._finish_step(connection, actor_id="OP-001", payload={"quantity": Decimal("1.0"), "occurred_at": datetime(2026, 7, 10, 12, 0, 0)})
        self.assertEqual(result["event"]["work_order_id"], "WO-E2E-MAVI-001")
        self.assertEqual(result["event"]["operation_code"], "OP10_ASSEMBLY_CLASSIFICATION")
        self.assertEqual(result["event"]["payload"]["action"], "finish")
        self.assertEqual(result["event"]["payload"]["quantity"], 1)
        self.assertEqual(result["event"]["payload"]["occurred_at"], "2026-07-10T12:00:00")

        for fragment in ("insert into mes.operation_events", "update mes.work_order_operation_steps", "update mes.work_order_operation_execution_state"):
            with self.subTest(fragment=fragment):
                connection = _Connection()
                _seed_finishable_execution_step(
                    connection.cursor_instance,
                    include_next_step=False,
                    operation_completion_policy="auto_close_on_required_steps",
                )
                before_state = deepcopy(connection.cursor_instance.execution_state_row)
                before_steps = deepcopy(connection.cursor_instance.execution_step_rows)
                connection.cursor_instance.raise_on_sql_fragment = fragment
                with self.assertRaises(RuntimeError):
                    self._finish_step(connection)
                self.assertFalse(connection.committed)
                self.assertEqual(connection.cursor_instance.execution_state_row, before_state)
                self.assertEqual(connection.cursor_instance.execution_step_rows, before_steps)
                self.assertEqual(connection.cursor_instance.operation_event_rows, [])

    def test_finish_execution_phase_writes_only_runtime_sidecar_tables(self) -> None:
        write_sql_constants = (mesql_v2.INSERT_OPERATION_EVENT_SQL, mesql_v2.UPDATE_EXECUTION_STEP_FINISHED_SQL, mesql_v2.UPDATE_EXECUTION_STATE_STEP_FINISHED_SQL)
        forbidden_tables = ("mes.work_orders", "mes.work_order_operations", "mes.station_queue", "mes.operation_approvals", "mes.production_flow_events", "mes.items", "mes.process_routes", "mes.route_operations", "mes.operation_steps", "mes.station_event_sources", "mes.locations", "mes.station_location_bindings")
        for sql in write_sql_constants:
            lowered = sql.lower()
            self.assertTrue(lowered.lstrip().startswith(("insert", "update")))
            for table_name in forbidden_tables:
                self.assertNotRegex(lowered, rf"\b(insert\s+into|update|delete\s+from)\s+{table_name}\b")

    def test_get_operation_event_by_idempotency_key_returns_none_when_missing(self) -> None:
        connection = _Connection()

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            event = get_operation_event_by_idempotency_key(AppConfig(db_enabled=True), "missing-key")

        self.assertIsNone(event)
        self.assertEqual(connection.cursor_instance.last_params["idempotency_key"], "missing-key")

    def test_get_operation_event_by_external_event_returns_existing_event(self) -> None:
        connection = _Connection()
        connection.cursor_instance.operation_event_rows = [_fake_operation_event()]

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            event = get_operation_event_by_external_event(
                AppConfig(db_enabled=True),
                "assembly_01",
                "color_sensor_entry",
                "sensor-001",
            )

        self.assertIsNotNone(event)
        self.assertEqual(event["event_id"], "OP_EVENT_ASSEMBLY_01_COLOR_SENSOR_ENTRY_sensor-001")
        self.assertEqual(connection.cursor_instance.last_params["station_code"], "ASSEMBLY_01")
        self.assertEqual(connection.cursor_instance.last_params["event_source"], "COLOR_SENSOR_ENTRY")

    def test_record_operation_event_inserts_event(self) -> None:
        connection = _Connection()

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            result = record_operation_event(
                AppConfig(db_enabled=True),
                work_order_operation_id="11111111-1111-1111-1111-111111111111",
                station_code="assembly_01",
                event_source="color_sensor_entry",
                event_type="step_start",
                idempotency_key="manual-key-001",
                actor_id="OP-001",
                payload={"source": "unit"},
            )

        executed_sql = "\n".join(sql.lower() for sql, _params in connection.cursor_instance.executed)
        self.assertTrue(result["inserted"])
        self.assertEqual(result["event"]["event_type"], "step_start")
        self.assertEqual(result["event"]["station_code"], "ASSEMBLY_01")
        self.assertEqual(result["event"]["event_source"], "COLOR_SENSOR_ENTRY")
        self.assertEqual(result["event"]["payload"]["actor_id"], "OP-001")
        self.assertTrue(connection.transaction_entered)
        self.assertTrue(connection.committed)
        self.assertIn("insert into mes.operation_events", executed_sql)

    def test_record_operation_event_uses_deterministic_idempotency_key_from_external_event(self) -> None:
        connection = _Connection()

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            result = record_operation_event(
                AppConfig(db_enabled=True),
                work_order_operation_id="11111111-1111-1111-1111-111111111111",
                station_code="assembly_01",
                event_source="color_sensor_entry",
                event_type="evidence",
                external_event_id="sensor-002",
            )

        self.assertTrue(result["inserted"])
        self.assertEqual(result["event"]["idempotency_key"], "ASSEMBLY_01:COLOR_SENSOR_ENTRY:sensor-002")
        insert_params = [
            params
            for sql, params in connection.cursor_instance.executed
            if "insert into mes.operation_events" in sql.lower()
        ][0]
        self.assertEqual(insert_params["idempotency_key"], "ASSEMBLY_01:COLOR_SENSOR_ENTRY:sensor-002")

    def test_record_operation_event_is_idempotent_by_idempotency_key(self) -> None:
        connection = _Connection()
        connection.cursor_instance.operation_event_rows = [
            _fake_operation_event(idempotency_key="manual-key-001", external_event_id=None)
        ]

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            result = record_operation_event(
                AppConfig(db_enabled=True),
                work_order_operation_id="11111111-1111-1111-1111-111111111111",
                station_code="ASSEMBLY_01",
                event_source="COLOR_SENSOR_ENTRY",
                event_type="step_start",
                idempotency_key="manual-key-001",
            )

        executed_sql = "\n".join(sql.lower() for sql, _params in connection.cursor_instance.executed)
        self.assertFalse(result["inserted"])
        self.assertEqual(result["event"]["idempotency_key"], "manual-key-001")
        self.assertNotIn("insert into mes.operation_events", executed_sql)

    def test_record_operation_event_is_idempotent_by_external_event(self) -> None:
        connection = _Connection()
        connection.cursor_instance.operation_event_rows = [_fake_operation_event()]

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            result = record_operation_event(
                AppConfig(db_enabled=True),
                work_order_operation_id="11111111-1111-1111-1111-111111111111",
                station_code="assembly_01",
                event_source="color_sensor_entry",
                event_type="step_start",
                idempotency_key="different-key",
                external_event_id="sensor-001",
            )

        executed_sql = "\n".join(sql.lower() for sql, _params in connection.cursor_instance.executed)
        self.assertFalse(result["inserted"])
        self.assertEqual(result["event"]["external_event_id"], "sensor-001")
        self.assertNotIn("insert into mes.operation_events", executed_sql)

    def test_record_operation_event_rejects_missing_identifiers(self) -> None:
        with self.assertRaises(mesql_v2.MesqlV2Error) as error:
            record_operation_event(
                AppConfig(db_enabled=True),
                work_order_operation_id="",
                station_code="ASSEMBLY_01",
                event_source="COLOR_SENSOR_ENTRY",
                event_type="step_start",
                idempotency_key="manual-key-001",
            )

        self.assertEqual(error.exception.detail, "OPERATION_EVENT_IDENTIFIER_REQUIRED")
        self.assertEqual(error.exception.status_code, 400)

    def test_record_operation_event_rejects_missing_idempotency(self) -> None:
        with self.assertRaises(mesql_v2.MesqlV2Error) as error:
            record_operation_event(
                AppConfig(db_enabled=True),
                work_order_operation_id="11111111-1111-1111-1111-111111111111",
                station_code="ASSEMBLY_01",
                event_source="COLOR_SENSOR_ENTRY",
                event_type="step_start",
            )

        self.assertEqual(error.exception.detail, "OPERATION_EVENT_IDEMPOTENCY_REQUIRED")
        self.assertEqual(error.exception.status_code, 400)

    def test_record_operation_event_rejects_invalid_event_type(self) -> None:
        with self.assertRaises(mesql_v2.MesqlV2Error) as error:
            record_operation_event(
                AppConfig(db_enabled=True),
                work_order_operation_id="11111111-1111-1111-1111-111111111111",
                station_code="ASSEMBLY_01",
                event_source="COLOR_SENSOR_ENTRY",
                event_type="start",
                idempotency_key="manual-key-001",
            )

        self.assertEqual(error.exception.detail, "INVALID_OPERATION_EVENT_TYPE")
        self.assertEqual(error.exception.status_code, 400)

    def test_record_operation_event_json_safe_payload(self) -> None:
        connection = _Connection()

        @contextmanager
        def fake_connection(_config):
            yield connection

        payload = {
            "quantity": Decimal("1.0"),
            "event_time": datetime(2026, 7, 9, 12, 0, 0),
            "operation_uuid": UUID("11111111-1111-1111-1111-111111111111"),
        }
        with patch.object(mesql_v2, "database_connection", fake_connection):
            result = record_operation_event(
                AppConfig(db_enabled=True),
                work_order_operation_id="11111111-1111-1111-1111-111111111111",
                station_code="ASSEMBLY_01",
                event_source="COLOR_SENSOR_ENTRY",
                event_type="evidence",
                external_event_id="sensor-json-safe",
                payload=payload,
            )

        self.assertTrue(result["inserted"])
        insert_params = [
            params
            for sql, params in connection.cursor_instance.executed
            if "insert into mes.operation_events" in sql.lower()
        ][0]
        inserted_payload = _unwrap_json_value(insert_params["payload"])
        self.assertEqual(inserted_payload["quantity"], 1)
        self.assertEqual(inserted_payload["event_time"], "2026-07-09T12:00:00")
        self.assertEqual(inserted_payload["operation_uuid"], "11111111-1111-1111-1111-111111111111")
        _assert_json_serializable_without_decimal(self, insert_params["payload"])

    def test_operation_event_phase_does_not_write_forbidden_tables(self) -> None:
        write_sql_constants = [mesql_v2.INSERT_OPERATION_EVENT_SQL]
        forbidden_write_tables = (
            "mes.work_order_operation_execution_state",
            "mes.work_order_operation_steps",
            "mes.operation_approvals",
            "mes.production_flow_events",
            "mes.work_orders",
            "mes.work_order_operations",
            "mes.station_queue",
        )

        for sql in write_sql_constants:
            lowered = sql.lower()
            self.assertTrue(lowered.lstrip().startswith("insert"))
            self.assertIn("insert into mes.operation_events", lowered)
            for table_name in forbidden_write_tables:
                self.assertNotRegex(lowered, rf"\b(insert\s+into|update|delete\s+from)\s+{table_name}\b")

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

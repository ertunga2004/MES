from __future__ import annotations

import json
import inspect
import unittest
from copy import deepcopy
from contextlib import ExitStack, contextmanager, nullcontext
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from threading import Barrier, Lock, Thread
from unittest.mock import patch
from uuid import UUID

from fastapi.testclient import TestClient
from psycopg.errors import UndefinedTable

import mes_web.app as app_module
from mes_web.config import AppConfig
from mes_web.db import mesql_v2
from mes_web.db.mesql_v2 import (
    complete_operation_v2,
    create_work_order_operation_route_binding,
    finish_execution_step,
    get_execution_state,
    get_location_by_code,
    get_item_by_code,
    get_operation_event_by_external_event,
    get_operation_event_by_idempotency_key,
    get_operation_step,
    get_exact_process_route,
    get_process_route,
    get_route_operation,
    get_route_operation_config,
    get_station_location_context,
    get_station_execution_config,
    get_work_order_operation_route_binding,
    get_work_order_operation_route_binding_by_id,
    get_work_order_release_snapshot,
    get_work_order_route_release,
    get_work_order_route_release_by_id,
    initialize_execution_state,
    list_locations,
    list_execution_steps,
    list_items,
    list_operation_steps,
    list_process_route_operations,
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
        self.work_order_operation_route_binding_rows: list[dict] = []
        self.inserted_work_order_operation_route_binding_row: dict | None = None
        self.hide_binding_by_operation = False
        self.hide_binding_by_id = False
        self.item_rows: list[dict] = []
        self.item_row: dict | None = None
        self.process_route_rows: list[dict] = []
        self.process_route_row: dict | None = None
        self.process_route_operation_rows: list[dict] = []
        self.route_operation_rows: list[dict] = []
        self.route_operation_row: dict | None = None
        self.work_order_route_release_rows: list[dict] = []
        self.release_work_order_row: dict | None = None
        self.release_operation_rows: list[dict] = []
        self.release_binding_rows: list[dict] = []
        self.release_initial_queue_row: dict | None = None
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
        self.exception_on_sql_fragment: tuple[str, Exception] | None = None
        self.exited = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.exited = True
        return None

    def execute(self, sql: str, params: dict | None = None) -> None:
        self.last_sql = sql
        self.last_params = dict(params or {})
        self.executed.append((sql, dict(params or {})))
        lowered = sql.lower()
        if (
            self.exception_on_sql_fragment is not None
            and self.exception_on_sql_fragment[0] in lowered
        ):
            raise self.exception_on_sql_fragment[1]
        if self.raise_on_sql_fragment and self.raise_on_sql_fragment in lowered:
            raise RuntimeError(f"forced cursor failure: {self.raise_on_sql_fragment}")
        if "insert into mes.work_order_operation_route_bindings" in lowered:
            binding_id = self.last_params["binding_id"]
            operation_id = self.last_params["work_order_operation_id"]
            conflict = any(
                row.get("binding_id") == binding_id
                or str(row.get("work_order_operation_id")) == operation_id
                for row in self.work_order_operation_route_binding_rows
            )
            self.inserted_work_order_operation_route_binding_row = None
            if not conflict:
                timestamp = datetime(2026, 7, 14, 11, 0, 0)
                row = {
                    "binding_pk": 101,
                    "binding_id": binding_id,
                    "work_order_operation_id": UUID(operation_id),
                    "route_operation_id": self.last_params["route_operation_id"],
                    "binding_source": self.last_params["binding_source"],
                    "bound_by": self.last_params["bound_by"],
                    "bound_at": timestamp,
                    "metadata": _unwrap_json_value(self.last_params["metadata"]),
                    "created_at": timestamp,
                }
                self.work_order_operation_route_binding_rows.append(row)
                self.inserted_work_order_operation_route_binding_row = row
        elif "insert into mes.work_order_operation_execution_state" in lowered:
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
        if "from mes.work_order_route_releases" in lowered:
            if "where order_id = %(work_order_id)s" in lowered:
                work_order_id = self.last_params.get("work_order_id")
                return next(
                    (
                        row
                        for row in self.work_order_route_release_rows
                        if row.get("order_id") == work_order_id
                    ),
                    None,
                )
            if "where release_id = %(release_id)s" in lowered:
                release_id = self.last_params.get("release_id")
                return next(
                    (
                        row
                        for row in self.work_order_route_release_rows
                        if row.get("release_id") == release_id
                    ),
                    None,
                )
        if (
            "from mes.process_routes" in lowered
            and "version = %(route_version)s" in lowered
        ):
            route_code = self.last_params.get("route_code")
            route_version = self.last_params.get("route_version")
            for row in self.process_route_rows:
                if (
                    row.get("route_code") == route_code
                    and row.get("version") == route_version
                ):
                    return row
            return None
        if (
            "from mes.work_orders" in lowered
            and "where order_id = %(work_order_id)s" in lowered
        ):
            if (
                self.release_work_order_row is not None
                and self.release_work_order_row.get("order_id")
                == self.last_params.get("work_order_id")
            ):
                return self.release_work_order_row
            return None
        if (
            "from mes.station_queue" in lowered
            and "work_order_operation_id = %(work_order_operation_id)s::uuid"
            in lowered
            and "for update" not in lowered
        ):
            row = self.release_initial_queue_row
            if row is None:
                return None
            if (
                str(row.get("work_order_operation_id"))
                == str(self.last_params.get("work_order_operation_id"))
                and row.get("order_id") == self.last_params.get("work_order_id")
                and row.get("station_code") == self.last_params.get("station_code")
            ):
                return row
            return None
        if (
            "insert into mes.work_order_operation_route_bindings" in lowered
            and "returning" in lowered
        ):
            return self.inserted_work_order_operation_route_binding_row
        if "from mes.work_order_operation_route_bindings" in lowered:
            if "where work_order_operation_id" in lowered:
                if self.hide_binding_by_operation:
                    return None
                operation_id = self.last_params.get("work_order_operation_id")
                return next(
                    (
                        row
                        for row in self.work_order_operation_route_binding_rows
                        if str(row.get("work_order_operation_id")) == operation_id
                    ),
                    None,
                )
            if "where binding_id" in lowered:
                if self.hide_binding_by_id:
                    return None
                binding_id = self.last_params.get("binding_id")
                return next(
                    (
                        row
                        for row in self.work_order_operation_route_binding_rows
                        if row.get("binding_id") == binding_id
                    ),
                    None,
                )
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
        if (
            "from mes.route_operations operation" in lowered
            and "join mes.process_routes route" in lowered
        ):
            process_route_id = self.last_params.get("process_route_id")
            route = next(
                (
                    row
                    for row in self.process_route_rows
                    if row.get("route_id") == process_route_id
                ),
                None,
            )
            if route is None:
                return []
            return sorted(
                [
                    row
                    for row in self.process_route_operation_rows
                    if row.get("route_code") == route.get("route_code")
                    and row.get("route_version") == route.get("version")
                ],
                key=lambda row: (
                    row.get("sequence_no", 0),
                    row.get("route_operation_id", ""),
                ),
            )
        if (
            "from mes.work_order_operations" in lowered
            and "where order_id = %(work_order_id)s" in lowered
            and "for update" not in lowered
        ):
            work_order_id = self.last_params.get("work_order_id")
            return sorted(
                [
                    row
                    for row in self.release_operation_rows
                    if row.get("order_id") == work_order_id
                ],
                key=lambda row: (
                    row.get("sequence_no", 0),
                    str(row.get("work_order_operation_id", "")),
                ),
            )
        if (
            "from mes.work_order_operation_route_bindings binding" in lowered
            and "join mes.work_order_operations operation" in lowered
        ):
            operation_sequence = {
                str(row.get("work_order_operation_id")): row.get(
                    "sequence_no",
                    0,
                )
                for row in self.release_operation_rows
                if row.get("order_id") == self.last_params.get("work_order_id")
            }
            return sorted(
                [
                    row
                    for row in self.release_binding_rows
                    if str(row.get("work_order_operation_id"))
                    in operation_sequence
                ],
                key=lambda row: (
                    operation_sequence[str(row.get("work_order_operation_id"))],
                    str(row.get("work_order_operation_id")),
                    row.get("binding_id", ""),
                ),
            )
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
        self.transaction_rolled_back = False
        self.transaction_sql_history: list[tuple[str, dict]] = []

    def cursor(self):
        return self.cursor_instance

    def transaction(self):
        connection = self

        class _Transaction:
            def __enter__(self):
                connection.transaction_entered = True
                self.snapshot = deepcopy(connection.cursor_instance.__dict__)
                self.start_index = len(connection.cursor_instance.executed)
                return self

            def __exit__(self, exc_type, *_args):
                connection.transaction_sql_history = deepcopy(
                    connection.cursor_instance.executed[self.start_index :]
                )
                if exc_type is not None:
                    connection.cursor_instance.__dict__.clear()
                    connection.cursor_instance.__dict__.update(self.snapshot)
                    connection.transaction_rolled_back = True
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


@contextmanager
def _yield_connection(connection):
    yield connection


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


def _fake_work_order_operation_route_binding(
    *,
    binding_pk: int = 101,
    binding_id: str = "BINDING-WO-OP-001",
    work_order_operation_id: UUID | None = None,
    route_operation_id: str = "ROUTE_BOX_PACKAGING_V2_OP10",
    binding_source: str = "manual_setup",
    bound_by: str = "SYSTEM",
    metadata: dict | None = None,
) -> dict:
    timestamp = datetime(2026, 7, 14, 10, 0, 0)
    return {
        "binding_pk": binding_pk,
        "binding_id": binding_id,
        "work_order_operation_id": work_order_operation_id
        or UUID("11111111-2222-3333-4444-555555555555"),
        "route_operation_id": route_operation_id,
        "binding_source": binding_source,
        "bound_by": bound_by,
        "bound_at": timestamp,
        "metadata": metadata if metadata is not None else {"purpose": "unit_test"},
        "created_at": timestamp,
    }


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
    route_id: str | None = None,
    version: int = 1,
    item_code: str = "PACKAGED_PRODUCT",
    active: bool = True,
    metadata: dict | None = None,
) -> dict:
    return {
        "route_id": route_id or route_code,
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


def _fake_work_order_route_release(
    *,
    release_id: str = "RELEASE-V2-EXAMPLE-001",
    order_id: str = "WO-RELEASE-001",
    process_route_id: str = "ROUTE_BOX_PACKAGING_V2",
    route_code: str = "ROUTE_BOX_PACKAGING_V2",
    route_version: int = 2,
    metadata: dict | None = None,
) -> dict:
    timestamp = datetime(2026, 7, 15, 12, 0, 0)
    return {
        "release_pk": 1,
        "release_id": release_id,
        "order_id": order_id,
        "process_route_id": process_route_id,
        "route_code": route_code,
        "route_version": route_version,
        "release_mode": "route_generated",
        "release_source": "local_planning",
        "released_by": "SCHEMA_SMOKE",
        "released_at": timestamp,
        "route_operation_count": 2,
        "operation_set_digest": (
            "4063a5c72fd4d38f11757a4bf1115f83"
            "e1c05e8b97624deb808193c5d0fcb2e2"
        ),
        "metadata": metadata if metadata is not None else {"purpose": "unit_test"},
        "created_at": timestamp,
    }


def _fake_release_work_order(
    order_id: str = "WO-RELEASE-001",
    *,
    metadata: dict | None = None,
) -> dict:
    timestamp = datetime(2026, 7, 15, 11, 0, 0)
    return {
        "work_order_pk": 42,
        "order_id": order_id,
        "erp_type": "LOCAL",
        "status": "queued",
        "product_code": "PACKAGED_PRODUCT",
        "target_quantity": 5,
        "started_at": None,
        "completed_at": None,
        "source_system": "mes_web",
        "source_file": None,
        "external_ref": "schema-smoke",
        "payload": {"source": "unit_test"},
        "metadata": metadata if metadata is not None else {"released": True},
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def _fake_release_operation(
    work_order_operation_id: str,
    *,
    order_id: str = "WO-RELEASE-001",
    sequence_no: int = 10,
    station_code: str = "ASSEMBLY_01",
) -> dict:
    timestamp = datetime(2026, 7, 15, 12, 0, 0)
    return {
        "work_order_operation_id": UUID(work_order_operation_id),
        "order_id": order_id,
        "operation_no": sequence_no,
        "operation_code": f"OP{sequence_no}",
        "operation_name": f"Operation {sequence_no}",
        "station_code": station_code,
        "status": "queued" if sequence_no == 10 else "planned",
        "planned_quantity": Decimal("5.000000"),
        "good_quantity": Decimal("0.000000"),
        "scrap_quantity": Decimal("0.000000"),
        "uom_code": "piece",
        "started_at": None,
        "completed_at": None,
        "sequence_no": sequence_no,
        "mesql_work_order_operation_id": None,
        "payload": {"source": "work_order_release"},
        "metadata": {"sequence": sequence_no},
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def _fake_release_initial_queue(
    work_order_operation_id: str,
    *,
    order_id: str = "WO-RELEASE-001",
    station_code: str = "ASSEMBLY_01",
) -> dict:
    timestamp = datetime(2026, 7, 15, 12, 0, 0)
    return {
        "station_queue_pk": 77,
        "station_code": station_code,
        "order_id": order_id,
        "queue_rank": 0,
        "status": "queued",
        "source": "work_order_release",
        "payload": {},
        "metadata": {"purpose": "release"},
        "created_at": timestamp,
        "updated_at": timestamp,
        "work_order_operation_id": UUID(work_order_operation_id),
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


def _seed_matching_runtime_binding(
    cursor: _Cursor,
    *,
    work_order_operation_id: str = "11111111-1111-1111-1111-111111111111",
    route_operation_id: str = "ROUTE_BOX_PACKAGING_V1_OP10",
) -> None:
    cursor.work_order_operation_route_binding_rows = [
        _fake_work_order_operation_route_binding(
            work_order_operation_id=UUID(work_order_operation_id),
            route_operation_id=route_operation_id,
        )
    ]


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
    @staticmethod
    def _binding_create_kwargs(**overrides):
        values = {
            "binding_id": "BINDING-WO-OP-001",
            "work_order_operation_id": "11111111-2222-3333-4444-555555555555",
            "route_operation_id": "ROUTE_BOX_PACKAGING_V2_OP10",
            "binding_source": "manual_setup",
            "bound_by": "SYSTEM",
            "metadata": {"purpose": "unit_test"},
        }
        values.update(overrides)
        return values

    def _create_binding(self, connection=None, **overrides):
        connection = connection or _Connection()
        with patch.object(
            mesql_v2,
            "database_connection",
            side_effect=lambda _config: _yield_connection(connection),
        ):
            result = create_work_order_operation_route_binding(
                AppConfig(db_enabled=True),
                **self._binding_create_kwargs(**overrides),
            )
        return result, connection

    def _assert_binding_conflict(self, connection, **overrides) -> None:
        with patch.object(
            mesql_v2,
            "database_connection",
            side_effect=lambda _config: _yield_connection(connection),
        ):
            with self.assertRaises(mesql_v2.MesqlV2Error) as error:
                create_work_order_operation_route_binding(
                    AppConfig(db_enabled=True),
                    **self._binding_create_kwargs(**overrides),
                )
        self.assertEqual(
            error.exception.detail,
            "WORK_ORDER_OPERATION_ROUTE_BINDING_CONFLICT",
        )
        self.assertEqual(error.exception.status_code, 409)

    def _assert_binding_validation_error(self, detail: str, **overrides) -> None:
        with patch.object(mesql_v2, "database_connection") as connection_factory:
            with self.assertRaises(mesql_v2.MesqlV2Error) as error:
                create_work_order_operation_route_binding(
                    AppConfig(db_enabled=True),
                    **self._binding_create_kwargs(**overrides),
                )
        self.assertEqual(error.exception.detail, detail)
        self.assertEqual(error.exception.status_code, 400)
        connection_factory.assert_not_called()

    def _initialize_runtime(self, connection: _Connection, **overrides):
        values = {
            "work_order_operation_id": "11111111-1111-1111-1111-111111111111",
            "route_operation_id": "ROUTE_BOX_PACKAGING_V1_OP10",
            "station_code": "ASSEMBLY_01",
        }
        values.update(overrides)
        with patch.object(
            mesql_v2,
            "database_connection",
            side_effect=lambda _config: _yield_connection(connection),
        ):
            return initialize_execution_state(
                AppConfig(db_enabled=True),
                **values,
            )

    @staticmethod
    def _release_pairs() -> list[dict]:
        return [
            {
                "sequence_no": 10,
                "route_operation_id": "ROUTE_BOX_PACKAGING_V2_OP10",
                "work_order_operation_id": (
                    "5258d822-55bd-56b1-81ba-7f89193ba4eb"
                ),
            },
            {
                "sequence_no": 20,
                "route_operation_id": "ROUTE_BOX_PACKAGING_V2_OP20",
                "work_order_operation_id": (
                    "26c50f67-2519-5e29-a958-e39eca44934e"
                ),
            },
        ]

    def _seed_release_snapshot(self, connection: _Connection) -> None:
        cursor = connection.cursor_instance
        pairs = self._release_pairs()
        cursor.work_order_route_release_rows = [
            _fake_work_order_route_release()
        ]
        cursor.release_work_order_row = _fake_release_work_order()
        cursor.release_operation_rows = [
            _fake_release_operation(
                pairs[1]["work_order_operation_id"],
                sequence_no=20,
                station_code="PACKAGING_01",
            ),
            _fake_release_operation(
                pairs[0]["work_order_operation_id"],
                sequence_no=10,
                station_code="ASSEMBLY_01",
            ),
        ]
        cursor.release_binding_rows = [
            _fake_work_order_operation_route_binding(
                binding_pk=202,
                binding_id=mesql_v2._derive_work_order_release_binding_id(
                    "RELEASE-V2-EXAMPLE-001",
                    pairs[1]["route_operation_id"],
                ),
                work_order_operation_id=UUID(
                    pairs[1]["work_order_operation_id"]
                ),
                route_operation_id=pairs[1]["route_operation_id"],
                binding_source="work_order_release",
            ),
            _fake_work_order_operation_route_binding(
                binding_pk=201,
                binding_id=mesql_v2._derive_work_order_release_binding_id(
                    "RELEASE-V2-EXAMPLE-001",
                    pairs[0]["route_operation_id"],
                ),
                work_order_operation_id=UUID(
                    pairs[0]["work_order_operation_id"]
                ),
                route_operation_id=pairs[0]["route_operation_id"],
                binding_source="work_order_release",
            ),
        ]
        cursor.release_initial_queue_row = _fake_release_initial_queue(
            pairs[0]["work_order_operation_id"]
        )

    @staticmethod
    def _call_read(connection: _Connection, helper, *args):
        with patch.object(
            mesql_v2,
            "database_connection",
            side_effect=lambda _config: _yield_connection(connection),
        ):
            return helper(AppConfig(db_enabled=True), *args)

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

    def test_binding_read_sql_is_select_only_and_explicit(self) -> None:
        expected_columns = (
            "binding_pk",
            "binding_id",
            "work_order_operation_id",
            "route_operation_id",
            "binding_source",
            "bound_by",
            "bound_at",
            "metadata",
            "created_at",
        )
        for sql in (
            mesql_v2.SELECT_WORK_ORDER_OPERATION_ROUTE_BINDING_SQL,
            mesql_v2.SELECT_WORK_ORDER_OPERATION_ROUTE_BINDING_BY_ID_SQL,
        ):
            with self.subTest(sql=sql):
                lowered = sql.lower()
                select_clause = lowered.split("from", 1)[0]
                self.assertTrue(lowered.lstrip().startswith("select"))
                self.assertNotIn("*", select_clause)
                for column in expected_columns:
                    self.assertRegex(select_clause, rf"\b{column}\b")
                self.assertNotRegex(
                    lowered,
                    r"\b(insert|update|delete|drop|truncate|alter|create|call)\b",
                )
                self.assertNotRegex(lowered, r"\bfor\s+update\b|\block\s+table\b")

    def test_binding_read_sql_has_no_inference_or_forbidden_tables(self) -> None:
        forbidden_terms = (
            "station_code",
            "operation_code",
            "sequence_no",
            "route_code",
            "route_version",
            "latest active",
        )
        forbidden_tables = (
            "mes.work_order_operations",
            "mes.route_operations",
            "mes.work_orders",
            "mes.station_queue",
            "mes.work_order_operation_execution_state",
        )
        for sql in (
            mesql_v2.SELECT_WORK_ORDER_OPERATION_ROUTE_BINDING_SQL,
            mesql_v2.SELECT_WORK_ORDER_OPERATION_ROUTE_BINDING_BY_ID_SQL,
        ):
            with self.subTest(sql=sql):
                lowered = sql.lower()
                self.assertEqual(
                    lowered.count("from mes.work_order_operation_route_bindings"),
                    1,
                )
                self.assertNotIn(" join ", lowered)
                for term in forbidden_terms:
                    self.assertNotIn(term, lowered)
                for table_name in forbidden_tables:
                    self.assertNotIn(table_name, lowered)

    def test_get_work_order_operation_route_binding_maps_exact_row(self) -> None:
        connection = _Connection()
        connection.cursor_instance.work_order_operation_route_binding_rows = [
            _fake_work_order_operation_route_binding()
        ]

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            binding = get_work_order_operation_route_binding(
                AppConfig(db_enabled=True),
                "11111111-2222-3333-4444-555555555555",
            )

        self.assertEqual(
            binding,
            {
                "binding_pk": 101,
                "binding_id": "BINDING-WO-OP-001",
                "work_order_operation_id": "11111111-2222-3333-4444-555555555555",
                "route_operation_id": "ROUTE_BOX_PACKAGING_V2_OP10",
                "binding_source": "manual_setup",
                "bound_by": "SYSTEM",
                "bound_at": "2026-07-14T10:00:00",
                "metadata": {"purpose": "unit_test"},
                "created_at": "2026-07-14T10:00:00",
            },
        )
        self.assertEqual(
            connection.cursor_instance.last_params["work_order_operation_id"],
            "11111111-2222-3333-4444-555555555555",
        )

    def test_get_work_order_operation_route_binding_returns_none_when_missing(self) -> None:
        connection = _Connection()

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            binding = get_work_order_operation_route_binding(
                AppConfig(db_enabled=True),
                "11111111-2222-3333-4444-555555555555",
            )

        self.assertIsNone(binding)

    def test_get_work_order_operation_route_binding_rejects_blank_uuid_before_db(self) -> None:
        with patch.object(mesql_v2, "database_connection") as connection_factory:
            with self.assertRaises(mesql_v2.MesqlV2Error) as error:
                get_work_order_operation_route_binding(AppConfig(db_enabled=True), "   ")

        self.assertEqual(error.exception.detail, "WORK_ORDER_OPERATION_ID_REQUIRED")
        self.assertEqual(error.exception.status_code, 400)
        connection_factory.assert_not_called()

    def test_get_work_order_operation_route_binding_rejects_invalid_uuid_before_db(self) -> None:
        with patch.object(mesql_v2, "database_connection") as connection_factory:
            with self.assertRaises(mesql_v2.MesqlV2Error) as error:
                get_work_order_operation_route_binding(AppConfig(db_enabled=True), "not-a-uuid")

        self.assertEqual(error.exception.detail, "WORK_ORDER_OPERATION_ID_INVALID")
        self.assertEqual(error.exception.status_code, 400)
        connection_factory.assert_not_called()

    def test_get_work_order_operation_route_binding_by_id_maps_row_and_preserves_case(self) -> None:
        connection = _Connection()
        connection.cursor_instance.work_order_operation_route_binding_rows = [
            _fake_work_order_operation_route_binding(binding_id="Bind-Case-01")
        ]

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            binding = get_work_order_operation_route_binding_by_id(
                AppConfig(db_enabled=True),
                "  Bind-Case-01  ",
            )

        self.assertIsNotNone(binding)
        self.assertEqual(binding["binding_id"], "Bind-Case-01")
        self.assertEqual(connection.cursor_instance.last_params["binding_id"], "Bind-Case-01")

    def test_get_work_order_operation_route_binding_by_id_returns_none_when_missing(self) -> None:
        connection = _Connection()

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            binding = get_work_order_operation_route_binding_by_id(
                AppConfig(db_enabled=True),
                "MISSING-BINDING",
            )

        self.assertIsNone(binding)

    def test_get_work_order_operation_route_binding_by_id_rejects_blank_before_db(self) -> None:
        for binding_id in ("", "   "):
            with self.subTest(binding_id=binding_id):
                with patch.object(mesql_v2, "database_connection") as connection_factory:
                    with self.assertRaises(mesql_v2.MesqlV2Error) as error:
                        get_work_order_operation_route_binding_by_id(
                            AppConfig(db_enabled=True),
                            binding_id,
                        )
                self.assertEqual(error.exception.detail, "BINDING_ID_REQUIRED")
                connection_factory.assert_not_called()

    def test_get_work_order_operation_route_binding_by_id_rejects_non_string_before_db(self) -> None:
        with patch.object(mesql_v2, "database_connection") as connection_factory:
            with self.assertRaises(mesql_v2.MesqlV2Error) as error:
                get_work_order_operation_route_binding_by_id(
                    AppConfig(db_enabled=True),
                    None,
                )

        self.assertEqual(error.exception.detail, "BINDING_ID_INVALID")
        self.assertEqual(error.exception.status_code, 400)
        connection_factory.assert_not_called()

    def test_binding_read_helpers_match_database_disabled_contract(self) -> None:
        for helper, identifier in (
            (
                get_work_order_operation_route_binding,
                "11111111-2222-3333-4444-555555555555",
            ),
            (get_work_order_operation_route_binding_by_id, "BINDING-WO-OP-001"),
        ):
            with self.subTest(helper=helper.__name__):
                with self.assertRaises(mesql_v2.MesqlV2Error) as error:
                    helper(AppConfig(db_enabled=False), identifier)
                self.assertEqual(error.exception.detail, "DATABASE_DISABLED")
                self.assertEqual(error.exception.status_code, 503)

    def test_binding_read_helpers_do_not_commit(self) -> None:
        connection = _Connection()
        connection.cursor_instance.work_order_operation_route_binding_rows = [
            _fake_work_order_operation_route_binding()
        ]

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            get_work_order_operation_route_binding(
                AppConfig(db_enabled=True),
                "11111111-2222-3333-4444-555555555555",
            )
            get_work_order_operation_route_binding_by_id(
                AppConfig(db_enabled=True),
                "BINDING-WO-OP-001",
            )

        self.assertFalse(connection.committed)
        self.assertFalse(connection.transaction_entered)

    def test_binding_read_helper_propagates_database_error_and_cleans_up(self) -> None:
        connection = _Connection()
        connection.cursor_instance.raise_on_sql_fragment = (
            "from mes.work_order_operation_route_bindings"
        )
        cleanup = {"connection": False}

        @contextmanager
        def fake_connection(_config):
            try:
                yield connection
            finally:
                cleanup["connection"] = True

        with patch.object(mesql_v2, "database_connection", fake_connection):
            with self.assertRaisesRegex(RuntimeError, "forced cursor failure"):
                get_work_order_operation_route_binding(
                    AppConfig(db_enabled=True),
                    "11111111-2222-3333-4444-555555555555",
                )

        self.assertTrue(connection.cursor_instance.exited)
        self.assertTrue(cleanup["connection"])
        self.assertFalse(connection.committed)

    def test_binding_read_helper_missing_table_error_is_not_none(self) -> None:
        connection = _Connection()

        @contextmanager
        def fake_connection(_config):
            yield connection

        missing_table_error = RuntimeError(
            'relation "mes.work_order_operation_route_bindings" does not exist'
        )
        with patch.object(mesql_v2, "database_connection", fake_connection):
            with patch.object(
                connection.cursor_instance,
                "execute",
                side_effect=missing_table_error,
            ):
                with self.assertRaisesRegex(RuntimeError, "does not exist"):
                    get_work_order_operation_route_binding_by_id(
                        AppConfig(db_enabled=True),
                        "BINDING-WO-OP-001",
                    )

        self.assertTrue(connection.cursor_instance.exited)
        self.assertFalse(connection.committed)

    def test_binding_read_response_has_no_inferred_fields(self) -> None:
        connection = _Connection()
        connection.cursor_instance.work_order_operation_route_binding_rows = [
            _fake_work_order_operation_route_binding()
        ]

        @contextmanager
        def fake_connection(_config):
            yield connection

        with patch.object(mesql_v2, "database_connection", fake_connection):
            binding = get_work_order_operation_route_binding_by_id(
                AppConfig(db_enabled=True),
                "BINDING-WO-OP-001",
            )

        self.assertEqual(
            set(binding or {}),
            {
                "binding_pk",
                "binding_id",
                "work_order_operation_id",
                "route_operation_id",
                "binding_source",
                "bound_by",
                "bound_at",
                "metadata",
                "created_at",
            },
        )

    def test_binding_insert_sql_is_insert_only_with_explicit_shapes(self) -> None:
        sql = mesql_v2.INSERT_WORK_ORDER_OPERATION_ROUTE_BINDING_SQL
        lowered = sql.lower()
        insert_columns = [
            column.strip()
            for column in lowered.split("(", 1)[1].split(")", 1)[0].split(",")
        ]
        returning_columns = [
            column.strip()
            for column in lowered.split("returning", 1)[1].strip().split(",")
        ]

        self.assertEqual(
            insert_columns,
            [
                "binding_id",
                "work_order_operation_id",
                "route_operation_id",
                "binding_source",
                "bound_by",
                "metadata",
            ],
        )
        self.assertEqual(
            returning_columns,
            [
                "binding_pk",
                "binding_id",
                "work_order_operation_id",
                "route_operation_id",
                "binding_source",
                "bound_by",
                "bound_at",
                "metadata",
                "created_at",
            ],
        )
        self.assertEqual(
            lowered.count("insert into mes.work_order_operation_route_bindings"),
            1,
        )
        self.assertIn("on conflict do nothing", lowered)
        self.assertNotIn("do update", lowered)
        self.assertNotRegex(lowered, r"\b(update|delete|merge)\b")

    def test_binding_insert_sql_is_parameterized_and_has_no_inference(self) -> None:
        lowered = mesql_v2.INSERT_WORK_ORDER_OPERATION_ROUTE_BINDING_SQL.lower()

        for parameter in (
            "binding_id",
            "work_order_operation_id",
            "route_operation_id",
            "binding_source",
            "bound_by",
            "metadata",
        ):
            self.assertIn(f"%({parameter})s", lowered)
        for forbidden in (
            "station_code",
            "operation_code",
            "sequence_no",
            "route_code",
            "route_version",
            "product_code",
            "latest active",
            "execution_state",
        ):
            self.assertNotIn(forbidden, lowered)

    def test_create_binding_inserts_and_returns_exact_shape(self) -> None:
        result, connection = self._create_binding()

        self.assertTrue(result["created"])
        self.assertEqual(
            set(result["binding"]),
            {
                "binding_pk",
                "binding_id",
                "work_order_operation_id",
                "route_operation_id",
                "binding_source",
                "bound_by",
                "bound_at",
                "metadata",
                "created_at",
            },
        )
        self.assertEqual(
            result["binding"]["work_order_operation_id"],
            "11111111-2222-3333-4444-555555555555",
        )
        self.assertEqual(result["binding"]["metadata"], {"purpose": "unit_test"})
        _assert_iso_timestamp(self, result["binding"]["bound_at"])
        _assert_iso_timestamp(self, result["binding"]["created_at"])
        self.assertEqual(len(connection.cursor_instance.work_order_operation_route_binding_rows), 1)

    def test_create_binding_defaults_none_metadata_to_empty_object(self) -> None:
        result, connection = self._create_binding(metadata=None)
        insert_params = connection.cursor_instance.executed[0][1]

        self.assertEqual(result["binding"]["metadata"], {})
        self.assertEqual(_unwrap_json_value(insert_params["metadata"]), {})

    def test_create_binding_does_not_mutate_caller_metadata(self) -> None:
        metadata = {"nested": {"items": [1, {"enabled": True}]}}
        original = deepcopy(metadata)
        result, connection = self._create_binding(metadata=metadata)

        self.assertEqual(metadata, original)
        self.assertIsNot(_unwrap_json_value(connection.cursor_instance.executed[0][1]["metadata"]), metadata)
        result["binding"]["metadata"]["nested"]["items"].append(2)
        self.assertEqual(metadata, original)

    def test_create_binding_trims_and_preserves_caller_case(self) -> None:
        result, connection = self._create_binding(
            binding_id="  Bind-Case-01  ",
            work_order_operation_id="AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE",
            route_operation_id="  Route-Case-Op10  ",
            binding_source="  manual_setup  ",
            bound_by="  Actor-Case  ",
        )
        params = connection.cursor_instance.executed[0][1]

        self.assertEqual(result["binding"]["binding_id"], "Bind-Case-01")
        self.assertEqual(result["binding"]["route_operation_id"], "Route-Case-Op10")
        self.assertEqual(result["binding"]["bound_by"], "Actor-Case")
        self.assertEqual(params["work_order_operation_id"], "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

    def test_create_binding_uses_transaction_and_commits_insert(self) -> None:
        result, connection = self._create_binding()

        self.assertTrue(result["created"])
        self.assertTrue(connection.transaction_entered)
        self.assertTrue(connection.committed)
        self.assertFalse(connection.transaction_rolled_back)
        self.assertTrue(connection.cursor_instance.exited)

    def test_create_binding_exact_replay_returns_existing_row(self) -> None:
        connection = _Connection()
        existing = _fake_work_order_operation_route_binding()
        connection.cursor_instance.work_order_operation_route_binding_rows = [existing]

        result, connection = self._create_binding(connection)

        self.assertFalse(result["created"])
        self.assertEqual(result["binding"]["binding_pk"], 101)
        self.assertEqual(len(connection.cursor_instance.work_order_operation_route_binding_rows), 1)
        self.assertFalse(connection.committed)

    def test_create_binding_exact_replay_can_resolve_by_operation_lookup(self) -> None:
        connection = _Connection()
        connection.cursor_instance.work_order_operation_route_binding_rows = [
            _fake_work_order_operation_route_binding()
        ]
        connection.cursor_instance.hide_binding_by_id = True

        result, _connection = self._create_binding(connection)

        self.assertFalse(result["created"])
        self.assertEqual(result["binding"]["binding_id"], "BINDING-WO-OP-001")

    def test_create_binding_exact_replay_can_resolve_by_binding_id_lookup(self) -> None:
        connection = _Connection()
        connection.cursor_instance.work_order_operation_route_binding_rows = [
            _fake_work_order_operation_route_binding()
        ]
        connection.cursor_instance.hide_binding_by_operation = True

        result, _connection = self._create_binding(connection)

        self.assertFalse(result["created"])
        self.assertEqual(
            result["binding"]["work_order_operation_id"],
            "11111111-2222-3333-4444-555555555555",
        )

    def test_create_binding_exact_replay_preserves_existing_timestamps(self) -> None:
        connection = _Connection()
        connection.cursor_instance.work_order_operation_route_binding_rows = [
            _fake_work_order_operation_route_binding()
        ]

        result, _connection = self._create_binding(connection)

        self.assertEqual(result["binding"]["bound_at"], "2026-07-14T10:00:00")
        self.assertEqual(result["binding"]["created_at"], "2026-07-14T10:00:00")

    def test_create_binding_exact_replay_runs_no_update_delete_or_merge(self) -> None:
        connection = _Connection()
        connection.cursor_instance.work_order_operation_route_binding_rows = [
            _fake_work_order_operation_route_binding()
        ]

        result, connection = self._create_binding(connection)
        executed_sql = "\n".join(sql.lower() for sql, _params in connection.cursor_instance.executed)

        self.assertFalse(result["created"])
        self.assertEqual(len(connection.cursor_instance.work_order_operation_route_binding_rows), 1)
        self.assertNotIn("do update", executed_sql)
        self.assertNotRegex(executed_sql, r"\b(update|delete|merge)\b")

    def test_create_binding_conflicts_when_operation_has_different_route(self) -> None:
        connection = _Connection()
        connection.cursor_instance.work_order_operation_route_binding_rows = [
            _fake_work_order_operation_route_binding(route_operation_id="OTHER-ROUTE-OP")
        ]

        self._assert_binding_conflict(connection)

    def test_create_binding_conflicts_when_operation_has_different_binding_id(self) -> None:
        connection = _Connection()
        connection.cursor_instance.work_order_operation_route_binding_rows = [
            _fake_work_order_operation_route_binding(binding_id="OTHER-BINDING-ID")
        ]

        self._assert_binding_conflict(connection)

    def test_create_binding_conflicts_when_binding_id_has_different_operation(self) -> None:
        connection = _Connection()
        connection.cursor_instance.work_order_operation_route_binding_rows = [
            _fake_work_order_operation_route_binding(
                work_order_operation_id=UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
            )
        ]

        self._assert_binding_conflict(connection)

    def test_create_binding_conflicts_on_metadata_mismatch(self) -> None:
        connection = _Connection()
        connection.cursor_instance.work_order_operation_route_binding_rows = [
            _fake_work_order_operation_route_binding(metadata={"purpose": "different"})
        ]

        self._assert_binding_conflict(connection)

    def test_create_binding_conflicts_on_source_mismatch(self) -> None:
        connection = _Connection()
        connection.cursor_instance.work_order_operation_route_binding_rows = [
            _fake_work_order_operation_route_binding(binding_source="work_order_release")
        ]

        self._assert_binding_conflict(connection)

    def test_create_binding_conflicts_on_bound_by_mismatch(self) -> None:
        connection = _Connection()
        connection.cursor_instance.work_order_operation_route_binding_rows = [
            _fake_work_order_operation_route_binding(bound_by="OTHER-ACTOR")
        ]

        self._assert_binding_conflict(connection)

    def test_create_binding_rejects_crossed_unique_collision(self) -> None:
        connection = _Connection()
        connection.cursor_instance.work_order_operation_route_binding_rows = [
            _fake_work_order_operation_route_binding(
                binding_pk=201,
                work_order_operation_id=UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
            ),
            _fake_work_order_operation_route_binding(
                binding_pk=202,
                binding_id="OTHER-BINDING-ID",
            ),
        ]

        self._assert_binding_conflict(connection)

    def test_create_binding_conflict_rolls_back_and_never_returns_replay(self) -> None:
        connection = _Connection()
        existing = _fake_work_order_operation_route_binding(route_operation_id="OTHER-ROUTE-OP")
        connection.cursor_instance.work_order_operation_route_binding_rows = [existing]

        self._assert_binding_conflict(connection)

        self.assertTrue(connection.transaction_entered)
        self.assertTrue(connection.transaction_rolled_back)
        self.assertFalse(connection.committed)
        self.assertEqual(connection.cursor_instance.work_order_operation_route_binding_rows, [existing])

    def test_create_binding_rejects_blank_binding_id_before_db(self) -> None:
        for value in ("", "   "):
            with self.subTest(value=value):
                self._assert_binding_validation_error("BINDING_ID_REQUIRED", binding_id=value)

    def test_create_binding_rejects_non_string_binding_id_before_db(self) -> None:
        for value in (None, 1, True):
            with self.subTest(value=value):
                self._assert_binding_validation_error("BINDING_ID_INVALID", binding_id=value)

    def test_create_binding_rejects_blank_operation_uuid_before_db(self) -> None:
        self._assert_binding_validation_error(
            "WORK_ORDER_OPERATION_ID_REQUIRED",
            work_order_operation_id="   ",
        )

    def test_create_binding_rejects_invalid_operation_uuid_before_db(self) -> None:
        for value, detail in (
            ("not-a-uuid", "WORK_ORDER_OPERATION_ID_INVALID"),
            (None, "WORK_ORDER_OPERATION_ID_REQUIRED"),
            (12, "WORK_ORDER_OPERATION_ID_INVALID"),
        ):
            with self.subTest(value=value):
                self._assert_binding_validation_error(
                    detail,
                    work_order_operation_id=value,
                )

    def test_create_binding_rejects_invalid_route_operation_id_before_db(self) -> None:
        for value, detail in (
            ("", "ROUTE_OPERATION_ID_REQUIRED"),
            ("   ", "ROUTE_OPERATION_ID_REQUIRED"),
            (None, "ROUTE_OPERATION_ID_INVALID"),
            (10, "ROUTE_OPERATION_ID_INVALID"),
        ):
            with self.subTest(value=value):
                self._assert_binding_validation_error(
                    detail,
                    route_operation_id=value,
                )

    def test_create_binding_rejects_blank_binding_source_before_db(self) -> None:
        for value in ("", "   "):
            with self.subTest(value=value):
                self._assert_binding_validation_error(
                    "BINDING_SOURCE_REQUIRED",
                    binding_source=value,
                )

    def test_create_binding_rejects_unknown_and_non_string_sources_before_db(self) -> None:
        for value in ("MANUAL_SETUP", "migration_backfill", "unknown", None, 1):
            with self.subTest(value=value):
                self._assert_binding_validation_error(
                    "BINDING_SOURCE_INVALID",
                    binding_source=value,
                )

    def test_create_binding_accepts_both_exact_source_values(self) -> None:
        for source in ("manual_setup", "work_order_release"):
            with self.subTest(source=source):
                result, _connection = self._create_binding(binding_source=source)
                self.assertTrue(result["created"])
                self.assertEqual(result["binding"]["binding_source"], source)

    def test_create_binding_rejects_invalid_bound_by_before_db(self) -> None:
        for value, detail in (
            ("", "BOUND_BY_REQUIRED"),
            ("   ", "BOUND_BY_REQUIRED"),
            (None, "BOUND_BY_INVALID"),
            (10, "BOUND_BY_INVALID"),
        ):
            with self.subTest(value=value):
                self._assert_binding_validation_error(detail, bound_by=value)

    def test_create_binding_rejects_non_object_metadata_before_db(self) -> None:
        for value in ([], (), "metadata", 1, 1.5, True, False):
            with self.subTest(value=value):
                self._assert_binding_validation_error(
                    "BINDING_METADATA_INVALID",
                    metadata=value,
                )

    def test_create_binding_rejects_nested_non_json_metadata_before_db(self) -> None:
        self._assert_binding_validation_error(
            "BINDING_METADATA_INVALID",
            metadata={"not_json": {"set-value"}},
        )

    def test_create_binding_matches_database_disabled_contract(self) -> None:
        with self.assertRaises(mesql_v2.MesqlV2Error) as error:
            create_work_order_operation_route_binding(
                AppConfig(db_enabled=False),
                **self._binding_create_kwargs(),
            )

        self.assertEqual(error.exception.detail, "DATABASE_DISABLED")
        self.assertEqual(error.exception.status_code, 503)

    def test_create_binding_propagates_insert_error_and_rolls_back(self) -> None:
        connection = _Connection()
        connection.cursor_instance.raise_on_sql_fragment = (
            "insert into mes.work_order_operation_route_bindings"
        )

        with patch.object(
            mesql_v2,
            "database_connection",
            side_effect=lambda _config: _yield_connection(connection),
        ):
            with self.assertRaisesRegex(RuntimeError, "forced cursor failure"):
                create_work_order_operation_route_binding(
                    AppConfig(db_enabled=True),
                    **self._binding_create_kwargs(),
                )

        self.assertTrue(connection.transaction_rolled_back)
        self.assertFalse(connection.committed)
        self.assertEqual(connection.cursor_instance.work_order_operation_route_binding_rows, [])

    def test_create_binding_propagates_conflict_lookup_error(self) -> None:
        connection = _Connection()
        connection.cursor_instance.work_order_operation_route_binding_rows = [
            _fake_work_order_operation_route_binding()
        ]
        connection.cursor_instance.raise_on_sql_fragment = "where work_order_operation_id"

        with patch.object(
            mesql_v2,
            "database_connection",
            side_effect=lambda _config: _yield_connection(connection),
        ):
            with self.assertRaisesRegex(RuntimeError, "forced cursor failure"):
                create_work_order_operation_route_binding(
                    AppConfig(db_enabled=True),
                    **self._binding_create_kwargs(),
                )

        self.assertTrue(connection.transaction_rolled_back)
        self.assertFalse(connection.committed)

    def test_create_binding_propagates_parent_fk_error_without_resolver(self) -> None:
        connection = _Connection()
        cleanup = {"connection": False}

        @contextmanager
        def fake_connection(_config):
            try:
                yield connection
            finally:
                cleanup["connection"] = True

        with patch.object(mesql_v2, "database_connection", fake_connection):
            with patch.object(
                connection.cursor_instance,
                "execute",
                side_effect=RuntimeError("foreign key violation"),
            ):
                with self.assertRaisesRegex(RuntimeError, "foreign key violation"):
                    create_work_order_operation_route_binding(
                        AppConfig(db_enabled=True),
                        **self._binding_create_kwargs(),
                    )

        self.assertTrue(cleanup["connection"])
        self.assertTrue(connection.transaction_rolled_back)
        self.assertFalse(connection.committed)

    def test_create_binding_insert_and_replay_lookup_share_cursor_transaction(self) -> None:
        connection = _Connection()
        connection.cursor_instance.work_order_operation_route_binding_rows = [
            _fake_work_order_operation_route_binding()
        ]

        result, connection = self._create_binding(connection)
        sql_statements = [sql.lower() for sql, _params in connection.cursor_instance.executed]

        self.assertFalse(result["created"])
        self.assertTrue(connection.transaction_entered)
        self.assertEqual(len(sql_statements), 3)
        self.assertIn("insert into mes.work_order_operation_route_bindings", sql_statements[0])
        self.assertIn("where work_order_operation_id", sql_statements[1])
        self.assertIn("where binding_id", sql_statements[2])

    def test_create_binding_signature_exposes_only_caller_controlled_fields(self) -> None:
        signature = inspect.signature(create_work_order_operation_route_binding)

        self.assertEqual(
            list(signature.parameters),
            [
                "config",
                "binding_id",
                "work_order_operation_id",
                "route_operation_id",
                "binding_source",
                "bound_by",
                "metadata",
            ],
        )
        for forbidden in (
            "binding_pk",
            "bound_at",
            "created_at",
            "active",
            "updated_at",
            "effective_from",
            "effective_to",
            "superseded_by",
        ):
            self.assertNotIn(forbidden, signature.parameters)

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
        _seed_matching_runtime_binding(connection.cursor_instance)

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

    def test_runtime_init_binding_validation_reuses_select_only_sql(self) -> None:
        sql = mesql_v2.SELECT_WORK_ORDER_OPERATION_ROUTE_BINDING_SQL.lower()
        source = inspect.getsource(initialize_execution_state).lower()

        self.assertTrue(sql.lstrip().startswith("select"))
        self.assertEqual(sql.count("from mes.work_order_operation_route_bindings"), 1)
        self.assertNotRegex(sql, r"\b(insert|update|delete|merge|truncate)\b")
        self.assertIn("_get_work_order_operation_route_binding_with_cursor", source)
        self.assertNotIn("create_work_order_operation_route_binding", source)
        self.assertNotRegex(
            source,
            r"(insert\s+into|update|delete\s+from)\s+mes\.work_order_operation_route_bindings",
        )

    def test_runtime_init_binding_validation_has_no_inference_query(self) -> None:
        sql = mesql_v2.SELECT_WORK_ORDER_OPERATION_ROUTE_BINDING_SQL.lower()
        source = inspect.getsource(initialize_execution_state).lower()

        for forbidden in (
            "station_code",
            "operation_code",
            "sequence_no",
            "route_code",
            "route_version",
            "product_code",
            "latest active",
            "execution_state metadata",
        ):
            self.assertNotIn(forbidden, sql)
        self.assertNotIn("list_route_operations", source)
        self.assertNotIn("latest", source)

    def test_initialize_execution_state_public_signature_is_unchanged(self) -> None:
        signature = inspect.signature(initialize_execution_state)

        self.assertEqual(
            list(signature.parameters),
            [
                "config",
                "work_order_operation_id",
                "route_operation_id",
                "station_code",
                "actor_id",
            ],
        )

    def test_binding_helper_public_contracts_are_unchanged(self) -> None:
        self.assertEqual(
            list(inspect.signature(get_work_order_operation_route_binding).parameters),
            ["config", "work_order_operation_id"],
        )
        self.assertEqual(
            list(inspect.signature(get_work_order_operation_route_binding_by_id).parameters),
            ["config", "binding_id"],
        )
        self.assertEqual(
            list(inspect.signature(create_work_order_operation_route_binding).parameters),
            [
                "config",
                "binding_id",
                "work_order_operation_id",
                "route_operation_id",
                "binding_source",
                "bound_by",
                "metadata",
            ],
        )

    def test_initialize_execution_state_accepts_matching_binding(self) -> None:
        connection = _Connection()
        _seed_valid_route_operation_config(connection.cursor_instance)
        _seed_matching_runtime_binding(connection.cursor_instance)

        result = self._initialize_runtime(connection)

        self.assertTrue(result["initialized"])
        self.assertEqual(result["execution_state"]["execution_status"], "ready")
        self.assertEqual(len(result["steps"]), 1)

    def test_runtime_init_binding_lookup_precedes_state_and_step_inserts(self) -> None:
        connection = _Connection()
        _seed_valid_route_operation_config(connection.cursor_instance)
        _seed_matching_runtime_binding(connection.cursor_instance)

        self._initialize_runtime(connection)
        statements = [sql.lower() for sql, _params in connection.transaction_sql_history]
        binding_index = next(
            index
            for index, sql in enumerate(statements)
            if "from mes.work_order_operation_route_bindings" in sql
        )
        state_insert_index = next(
            index
            for index, sql in enumerate(statements)
            if "insert into mes.work_order_operation_execution_state" in sql
        )
        step_insert_index = next(
            index
            for index, sql in enumerate(statements)
            if "insert into mes.work_order_operation_steps" in sql
        )

        self.assertLess(binding_index, state_insert_index)
        self.assertLess(binding_index, step_insert_index)

    def test_runtime_init_binding_lookup_and_writes_share_transaction_cursor(self) -> None:
        connection = _Connection()
        _seed_valid_route_operation_config(connection.cursor_instance)
        _seed_matching_runtime_binding(connection.cursor_instance)

        self._initialize_runtime(connection)
        transaction_sql = "\n".join(
            sql.lower() for sql, _params in connection.transaction_sql_history
        )

        self.assertTrue(connection.transaction_entered)
        self.assertFalse(connection.transaction_rolled_back)
        self.assertIn("from mes.work_order_operation_route_bindings", transaction_sql)
        self.assertIn("insert into mes.work_order_operation_execution_state", transaction_sql)
        self.assertIn("insert into mes.work_order_operation_steps", transaction_sql)

    def test_runtime_init_return_shape_does_not_expose_binding(self) -> None:
        connection = _Connection()
        _seed_valid_route_operation_config(connection.cursor_instance)
        _seed_matching_runtime_binding(connection.cursor_instance)

        result = self._initialize_runtime(connection)

        self.assertEqual(
            set(result),
            {
                "status",
                "work_order_operation_id",
                "route_operation_id",
                "station_code",
                "initialized",
                "execution_state",
                "steps",
            },
        )
        for forbidden in (
            "binding",
            "binding_id",
            "binding_source",
            "bound_at",
            "binding_validated",
        ):
            self.assertNotIn(forbidden, result)

    def test_runtime_init_requires_binding_for_new_execution_state(self) -> None:
        connection = _Connection()
        _seed_valid_route_operation_config(connection.cursor_instance)

        with self.assertRaises(mesql_v2.MesqlV2Error) as error:
            self._initialize_runtime(connection)

        self.assertEqual(
            error.exception.detail,
            "WORK_ORDER_OPERATION_ROUTE_BINDING_REQUIRED",
        )
        self.assertEqual(error.exception.status_code, 409)
        self.assertTrue(connection.transaction_rolled_back)

    def test_missing_runtime_binding_performs_no_runtime_write(self) -> None:
        connection = _Connection()
        _seed_valid_route_operation_config(connection.cursor_instance)

        with self.assertRaises(mesql_v2.MesqlV2Error):
            self._initialize_runtime(connection)
        transaction_sql = "\n".join(
            sql.lower() for sql, _params in connection.transaction_sql_history
        )

        self.assertNotIn("insert into mes.work_order_operation_execution_state", transaction_sql)
        self.assertNotIn("insert into mes.work_order_operation_steps", transaction_sql)
        self.assertIsNone(connection.cursor_instance.execution_state_row)
        self.assertEqual(connection.cursor_instance.execution_step_rows, [])
        self.assertFalse(connection.committed)

    def test_missing_runtime_binding_does_not_infer_or_create_binding(self) -> None:
        connection = _Connection()
        _seed_valid_route_operation_config(connection.cursor_instance)

        with self.assertRaises(mesql_v2.MesqlV2Error):
            self._initialize_runtime(connection)
        transaction_sql = "\n".join(
            sql.lower() for sql, _params in connection.transaction_sql_history
        )

        self.assertEqual(
            transaction_sql.count("from mes.work_order_operation_route_bindings"),
            1,
        )
        self.assertNotIn("insert into mes.work_order_operation_route_bindings", transaction_sql)
        self.assertNotIn("from mes.route_operations", transaction_sql)
        self.assertNotIn("sequence_no", transaction_sql)

    def test_runtime_init_rejects_binding_route_mismatch(self) -> None:
        connection = _Connection()
        _seed_valid_route_operation_config(connection.cursor_instance)
        _seed_matching_runtime_binding(
            connection.cursor_instance,
            route_operation_id="ROUTE_BOX_PACKAGING_V1_OP20",
        )

        with self.assertRaises(mesql_v2.MesqlV2Error) as error:
            self._initialize_runtime(connection)

        self.assertEqual(
            error.exception.detail,
            "WORK_ORDER_OPERATION_ROUTE_BINDING_MISMATCH",
        )
        self.assertEqual(error.exception.status_code, 409)

    def test_runtime_binding_mismatch_performs_no_runtime_write(self) -> None:
        connection = _Connection()
        _seed_valid_route_operation_config(connection.cursor_instance)
        _seed_matching_runtime_binding(
            connection.cursor_instance,
            route_operation_id="ROUTE_BOX_PACKAGING_V1_OP20",
        )

        with self.assertRaises(mesql_v2.MesqlV2Error):
            self._initialize_runtime(connection)
        transaction_sql = "\n".join(
            sql.lower() for sql, _params in connection.transaction_sql_history
        )

        self.assertNotIn("insert into mes.work_order_operation_execution_state", transaction_sql)
        self.assertNotIn("insert into mes.work_order_operation_steps", transaction_sql)
        self.assertIsNone(connection.cursor_instance.execution_state_row)
        self.assertEqual(connection.cursor_instance.execution_step_rows, [])
        self.assertTrue(connection.transaction_rolled_back)

    def test_runtime_binding_mismatch_does_not_mutate_binding(self) -> None:
        connection = _Connection()
        _seed_valid_route_operation_config(connection.cursor_instance)
        _seed_matching_runtime_binding(
            connection.cursor_instance,
            route_operation_id="ROUTE_BOX_PACKAGING_V1_OP20",
        )
        before = deepcopy(
            connection.cursor_instance.work_order_operation_route_binding_rows
        )

        with self.assertRaises(mesql_v2.MesqlV2Error):
            self._initialize_runtime(connection)
        transaction_sql = "\n".join(
            sql.lower() for sql, _params in connection.transaction_sql_history
        )

        self.assertEqual(
            connection.cursor_instance.work_order_operation_route_binding_rows,
            before,
        )
        self.assertNotRegex(
            transaction_sql,
            r"(insert\s+into|update|delete\s+from)\s+mes\.work_order_operation_route_bindings",
        )

    def test_existing_execution_state_is_grandfathered_without_binding(self) -> None:
        connection = _Connection()
        _seed_valid_route_operation_config(connection.cursor_instance)
        connection.cursor_instance.execution_state_row = _fake_execution_state()
        connection.cursor_instance.execution_step_rows = [_fake_execution_step()]

        result = self._initialize_runtime(connection)

        self.assertFalse(result["initialized"])
        self.assertEqual(len(result["steps"]), 1)

    def test_grandfathered_runtime_does_not_query_binding_table(self) -> None:
        connection = _Connection()
        _seed_valid_route_operation_config(connection.cursor_instance)
        connection.cursor_instance.execution_state_row = _fake_execution_state()
        connection.cursor_instance.execution_step_rows = [_fake_execution_step()]

        self._initialize_runtime(connection)
        transaction_sql = "\n".join(
            sql.lower() for sql, _params in connection.transaction_sql_history
        )

        self.assertNotIn("from mes.work_order_operation_route_bindings", transaction_sql)

    def test_grandfathered_runtime_survives_missing_binding_table_behavior(self) -> None:
        connection = _Connection()
        _seed_valid_route_operation_config(connection.cursor_instance)
        connection.cursor_instance.execution_state_row = _fake_execution_state()
        connection.cursor_instance.execution_step_rows = [_fake_execution_step()]
        connection.cursor_instance.exception_on_sql_fragment = (
            "from mes.work_order_operation_route_bindings",
            UndefinedTable('relation "mes.work_order_operation_route_bindings" does not exist'),
        )

        result = self._initialize_runtime(connection)

        self.assertFalse(result["initialized"])
        self.assertFalse(connection.transaction_rolled_back)

    def test_grandfathered_runtime_preserves_state_fields_and_timestamps(self) -> None:
        connection = _Connection()
        _seed_valid_route_operation_config(connection.cursor_instance)
        state = _fake_execution_state(execution_status="active")
        state["current_step_code"] = "COLOR_SENSOR_ENTRY_EVIDENCE"
        state["started_at"] = datetime(2026, 7, 9, 11, 0, 0)
        connection.cursor_instance.execution_state_row = state
        connection.cursor_instance.execution_step_rows = [_fake_execution_step(status="active")]
        before = deepcopy(state)

        result = self._initialize_runtime(connection)

        self.assertFalse(result["initialized"])
        self.assertEqual(connection.cursor_instance.execution_state_row, before)
        self.assertEqual(result["execution_state"]["execution_status"], "active")
        self.assertEqual(
            result["execution_state"]["current_step_code"],
            "COLOR_SENSOR_ENTRY_EVIDENCE",
        )

    def test_grandfathered_runtime_does_not_duplicate_steps(self) -> None:
        connection = _Connection()
        _seed_valid_route_operation_config(connection.cursor_instance)
        connection.cursor_instance.execution_state_row = _fake_execution_state()
        connection.cursor_instance.execution_step_rows = [_fake_execution_step()]
        before = deepcopy(connection.cursor_instance.execution_step_rows)

        result = self._initialize_runtime(connection)

        self.assertFalse(result["initialized"])
        self.assertEqual(connection.cursor_instance.execution_step_rows, before)
        transaction_sql = "\n".join(
            sql.lower() for sql, _params in connection.transaction_sql_history
        )
        self.assertNotIn("insert into mes.work_order_operation_steps", transaction_sql)

    def test_new_runtime_ready_state_has_no_current_step(self) -> None:
        connection = _Connection()
        _seed_valid_route_operation_config(connection.cursor_instance)
        _seed_matching_runtime_binding(connection.cursor_instance)

        result = self._initialize_runtime(connection)

        self.assertTrue(result["initialized"])
        self.assertEqual(result["execution_state"]["execution_status"], "ready")
        self.assertIsNone(result["execution_state"]["current_step_code"])
        self.assertTrue(all(step["status"] == "pending" for step in result["steps"]))

    def test_new_runtime_initial_steps_are_pending_and_unstarted(self) -> None:
        connection = _Connection()
        _seed_valid_route_operation_config(connection.cursor_instance)
        _seed_matching_runtime_binding(connection.cursor_instance)

        result = self._initialize_runtime(connection)

        for step in result["steps"]:
            self.assertEqual(step["status"], "pending")
            self.assertIsNone(step["started_at"])
            self.assertIsNone(step["completed_at"])
            self.assertIsNone(step["started_by_event_id"])
            self.assertIsNone(step["completed_by_event_id"])

    def test_new_runtime_initialization_creates_no_start_event_evidence(self) -> None:
        connection = _Connection()
        _seed_valid_route_operation_config(connection.cursor_instance)
        _seed_matching_runtime_binding(connection.cursor_instance)

        self._initialize_runtime(connection)
        transaction_sql = "\n".join(
            sql.lower() for sql, _params in connection.transaction_sql_history
        )

        self.assertEqual(connection.cursor_instance.operation_event_rows, [])
        self.assertNotIn("insert into mes.operation_events", transaction_sql)
        self.assertNotIn("update mes.work_order_operation_execution_state", transaction_sql)
        self.assertNotIn("update mes.work_order_operation_steps", transaction_sql)

    def test_new_runtime_first_pending_step_remains_ordered_read_model(self) -> None:
        connection = _Connection()
        _seed_valid_route_operation_config(connection.cursor_instance)
        connection.cursor_instance.operation_step_rows.append(
            _fake_operation_step(step_code="ROBOT_ARM_DROP_COMPLETED", step_no=20)
        )
        _seed_matching_runtime_binding(connection.cursor_instance)

        result = self._initialize_runtime(connection)

        self.assertIsNone(result["execution_state"]["current_step_code"])
        self.assertEqual(
            [step["step_code"] for step in result["steps"]],
            ["COLOR_SENSOR_ENTRY_EVIDENCE", "ROBOT_ARM_DROP_COMPLETED"],
        )
        self.assertEqual(result["steps"][0]["status"], "pending")

    def test_matching_existing_route_replay_uses_stored_identity(self) -> None:
        connection = _Connection()
        _seed_valid_route_operation_config(connection.cursor_instance)
        state = _fake_execution_state()
        state["metadata"] = {
            "source": "runtime_engine_v0_phase1",
            "route_operation_id": "ROUTE_BOX_PACKAGING_V1_OP10",
        }
        connection.cursor_instance.execution_state_row = state
        connection.cursor_instance.execution_step_rows = [_fake_execution_step()]

        result = self._initialize_runtime(
            connection,
            route_operation_id="route_box_packaging_v1_op10",
        )

        self.assertFalse(result["initialized"])
        self.assertEqual(
            result["route_operation_id"],
            state["metadata"]["route_operation_id"],
        )

    def test_matching_existing_route_replay_skips_binding_lookup(self) -> None:
        connection = _Connection()
        _seed_valid_route_operation_config(connection.cursor_instance)
        state = _fake_execution_state()
        state["metadata"] = {"route_operation_id": "ROUTE_BOX_PACKAGING_V1_OP10"}
        connection.cursor_instance.execution_state_row = state
        connection.cursor_instance.execution_step_rows = [_fake_execution_step()]
        connection.cursor_instance.exception_on_sql_fragment = (
            "from mes.work_order_operation_route_bindings",
            UndefinedTable('relation "mes.work_order_operation_route_bindings" does not exist'),
        )

        result = self._initialize_runtime(connection)
        transaction_sql = "\n".join(
            sql.lower() for sql, _params in connection.transaction_sql_history
        )

        self.assertFalse(result["initialized"])
        self.assertNotIn("from mes.work_order_operation_route_bindings", transaction_sql)

    def test_matching_existing_route_replay_preserves_runtime_rows(self) -> None:
        connection = _Connection()
        _seed_valid_route_operation_config(connection.cursor_instance)
        state = _fake_execution_state(execution_status="active")
        state["metadata"] = {"route_operation_id": "ROUTE_BOX_PACKAGING_V1_OP10"}
        state["current_step_code"] = "COLOR_SENSOR_ENTRY_EVIDENCE"
        state["started_at"] = datetime(2026, 7, 9, 11, 0, 0)
        connection.cursor_instance.execution_state_row = state
        connection.cursor_instance.execution_step_rows = [
            _fake_execution_step(status="active")
        ]
        before_state = deepcopy(state)
        before_steps = deepcopy(connection.cursor_instance.execution_step_rows)

        result = self._initialize_runtime(connection)

        self.assertFalse(result["initialized"])
        self.assertEqual(connection.cursor_instance.execution_state_row, before_state)
        self.assertEqual(connection.cursor_instance.execution_step_rows, before_steps)

    def test_existing_state_wrong_route_raises_explicit_conflict(self) -> None:
        connection = _Connection()
        _seed_valid_route_operation_config(connection.cursor_instance)
        state = _fake_execution_state()
        state["metadata"] = {"route_operation_id": "ROUTE_BOX_PACKAGING_V2_OP10"}
        connection.cursor_instance.execution_state_row = state
        connection.cursor_instance.execution_step_rows = [_fake_execution_step()]

        with self.assertRaises(mesql_v2.MesqlV2Error) as error:
            self._initialize_runtime(connection)

        self.assertEqual(
            error.exception.detail,
            "EXECUTION_STATE_ROUTE_OPERATION_MISMATCH",
        )
        self.assertEqual(error.exception.status_code, 409)

    def test_existing_state_wrong_route_performs_no_runtime_or_binding_write(self) -> None:
        connection = _Connection()
        _seed_valid_route_operation_config(connection.cursor_instance)
        state = _fake_execution_state()
        state["metadata"] = {"route_operation_id": "ROUTE_BOX_PACKAGING_V2_OP10"}
        connection.cursor_instance.execution_state_row = state
        connection.cursor_instance.execution_step_rows = [_fake_execution_step()]
        before_state = deepcopy(state)
        before_steps = deepcopy(connection.cursor_instance.execution_step_rows)

        with self.assertRaises(mesql_v2.MesqlV2Error):
            self._initialize_runtime(connection)
        transaction_sql = "\n".join(
            sql.lower() for sql, _params in connection.transaction_sql_history
        )

        self.assertEqual(connection.cursor_instance.execution_state_row, before_state)
        self.assertEqual(connection.cursor_instance.execution_step_rows, before_steps)
        self.assertNotRegex(
            transaction_sql,
            r"(insert\s+into|update|delete\s+from)\s+mes\.(work_order_operation_execution_state|work_order_operation_steps|work_order_operation_route_bindings)",
        )
        self.assertNotIn("from mes.work_order_operation_route_bindings", transaction_sql)

    def test_existing_state_wrong_route_rolls_back_and_cleans_up(self) -> None:
        connection = _Connection()
        _seed_valid_route_operation_config(connection.cursor_instance)
        state = _fake_execution_state()
        state["metadata"] = {"route_operation_id": "ROUTE_BOX_PACKAGING_V2_OP10"}
        connection.cursor_instance.execution_state_row = state
        connection.cursor_instance.execution_step_rows = [_fake_execution_step()]
        cleanup = {"calls": 0}

        @contextmanager
        def fake_connection(_config):
            try:
                yield connection
            finally:
                cleanup["calls"] += 1

        with patch.object(mesql_v2, "database_connection", fake_connection):
            with self.assertRaises(mesql_v2.MesqlV2Error):
                initialize_execution_state(
                    AppConfig(db_enabled=True),
                    work_order_operation_id="11111111-1111-1111-1111-111111111111",
                    route_operation_id="ROUTE_BOX_PACKAGING_V1_OP10",
                    station_code="ASSEMBLY_01",
                )

        self.assertGreater(cleanup["calls"], 0)
        self.assertTrue(connection.transaction_rolled_back)
        self.assertFalse(connection.committed)

    def test_historical_state_without_route_identity_keeps_requested_response_identity(self) -> None:
        connection = _Connection()
        _seed_valid_route_operation_config(connection.cursor_instance)
        state = _fake_execution_state()
        state["metadata"] = {"source": "historical_runtime"}
        connection.cursor_instance.execution_state_row = state
        connection.cursor_instance.execution_step_rows = [_fake_execution_step()]

        result = self._initialize_runtime(connection)

        self.assertFalse(result["initialized"])
        self.assertEqual(result["route_operation_id"], "ROUTE_BOX_PACKAGING_V1_OP10")

    def test_historical_state_without_route_identity_preserves_rows_when_binding_table_missing(self) -> None:
        connection = _Connection()
        _seed_valid_route_operation_config(connection.cursor_instance)
        state = _fake_execution_state()
        state["metadata"] = {}
        connection.cursor_instance.execution_state_row = state
        connection.cursor_instance.execution_step_rows = [_fake_execution_step()]
        connection.cursor_instance.exception_on_sql_fragment = (
            "from mes.work_order_operation_route_bindings",
            UndefinedTable('relation "mes.work_order_operation_route_bindings" does not exist'),
        )
        before_state = deepcopy(state)
        before_steps = deepcopy(connection.cursor_instance.execution_step_rows)

        result = self._initialize_runtime(connection)

        self.assertFalse(result["initialized"])
        self.assertEqual(connection.cursor_instance.execution_state_row, before_state)
        self.assertEqual(connection.cursor_instance.execution_step_rows, before_steps)
        self.assertFalse(connection.transaction_rolled_back)

    def test_new_runtime_init_propagates_binding_undefined_table(self) -> None:
        connection = _Connection()
        _seed_valid_route_operation_config(connection.cursor_instance)
        connection.cursor_instance.exception_on_sql_fragment = (
            "from mes.work_order_operation_route_bindings",
            UndefinedTable('relation "mes.work_order_operation_route_bindings" does not exist'),
        )

        with self.assertRaises(UndefinedTable):
            self._initialize_runtime(connection)

        self.assertTrue(connection.transaction_rolled_back)
        self.assertIsNone(connection.cursor_instance.execution_state_row)

    def test_new_runtime_init_propagates_generic_binding_select_error(self) -> None:
        connection = _Connection()
        _seed_valid_route_operation_config(connection.cursor_instance)
        connection.cursor_instance.exception_on_sql_fragment = (
            "from mes.work_order_operation_route_bindings",
            RuntimeError("binding lookup failed"),
        )
        cleanup = {"connection": False}

        @contextmanager
        def fake_connection(_config):
            try:
                yield connection
            finally:
                cleanup["connection"] = True

        with patch.object(mesql_v2, "database_connection", fake_connection):
            with self.assertRaisesRegex(RuntimeError, "binding lookup failed"):
                initialize_execution_state(
                    AppConfig(db_enabled=True),
                    work_order_operation_id="11111111-1111-1111-1111-111111111111",
                    route_operation_id="ROUTE_BOX_PACKAGING_V1_OP10",
                    station_code="ASSEMBLY_01",
                )

        self.assertTrue(cleanup["connection"])
        self.assertTrue(connection.transaction_rolled_back)
        self.assertFalse(connection.committed)
        self.assertIsNone(connection.cursor_instance.execution_state_row)

    def test_matching_binding_wrong_station_preserves_station_guard(self) -> None:
        connection = _Connection()
        _seed_valid_route_operation_config(connection.cursor_instance)
        _seed_matching_runtime_binding(connection.cursor_instance)

        with self.assertRaises(mesql_v2.MesqlV2Error) as error:
            self._initialize_runtime(connection, station_code="PACKAGING_01")

        self.assertEqual(error.exception.detail, "ROUTE_OPERATION_STATION_MISMATCH")
        self.assertEqual(error.exception.status_code, 409)
        self.assertFalse(connection.transaction_entered)
        self.assertIsNone(connection.cursor_instance.execution_state_row)

    def test_matching_binding_creates_exact_config_step_count(self) -> None:
        connection = _Connection()
        _seed_valid_route_operation_config(connection.cursor_instance)
        connection.cursor_instance.operation_step_rows.append(
            _fake_operation_step(step_code="ROBOT_ARM_DROP_COMPLETED", step_no=20)
        )
        _seed_matching_runtime_binding(connection.cursor_instance)

        result = self._initialize_runtime(connection)

        self.assertTrue(result["initialized"])
        self.assertEqual(len(result["steps"]), 2)
        self.assertEqual(
            [step["step_code"] for step in result["steps"]],
            ["COLOR_SENSOR_ENTRY_EVIDENCE", "ROBOT_ARM_DROP_COMPLETED"],
        )

    def test_matching_binding_keeps_work_order_operation_runtime_identity(self) -> None:
        connection = _Connection()
        _seed_valid_route_operation_config(connection.cursor_instance)
        _seed_matching_runtime_binding(connection.cursor_instance)

        result = self._initialize_runtime(connection)

        operation_id = "11111111-1111-1111-1111-111111111111"
        self.assertEqual(result["work_order_operation_id"], operation_id)
        self.assertEqual(
            result["execution_state"]["work_order_operation_id"],
            operation_id,
        )
        self.assertTrue(
            all(step["work_order_operation_id"] == operation_id for step in result["steps"])
        )

    def test_runtime_step_insert_failure_rolls_back_matching_init(self) -> None:
        connection = _Connection()
        _seed_valid_route_operation_config(connection.cursor_instance)
        _seed_matching_runtime_binding(connection.cursor_instance)
        connection.cursor_instance.raise_on_sql_fragment = (
            "insert into mes.work_order_operation_steps"
        )

        with self.assertRaisesRegex(RuntimeError, "forced cursor failure"):
            self._initialize_runtime(connection)

        self.assertTrue(connection.transaction_rolled_back)
        self.assertFalse(connection.committed)
        self.assertIsNone(connection.cursor_instance.execution_state_row)
        self.assertEqual(connection.cursor_instance.execution_step_rows, [])
        transaction_sql = "\n".join(
            sql.lower() for sql, _params in connection.transaction_sql_history
        )
        self.assertIn("insert into mes.work_order_operation_execution_state", transaction_sql)
        self.assertIn("insert into mes.work_order_operation_steps", transaction_sql)

    def test_existing_operation_station_mismatch_guard_is_preserved(self) -> None:
        connection = _Connection()
        _seed_valid_route_operation_config(connection.cursor_instance)
        connection.cursor_instance.runtime_operation_row = _fake_runtime_operation(
            station_code="PACKAGING_01"
        )
        connection.cursor_instance.execution_state_row = _fake_execution_state()

        with self.assertRaises(mesql_v2.MesqlV2Error) as error:
            self._initialize_runtime(connection)

        self.assertEqual(
            error.exception.detail,
            "WORK_ORDER_OPERATION_STATION_MISMATCH",
        )
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

    def test_work_order_release_public_helper_signatures_are_exact(self) -> None:
        expected = {
            get_work_order_route_release: ["config", "work_order_id"],
            get_work_order_route_release_by_id: ["config", "release_id"],
            get_exact_process_route: ["config", "route_code", "route_version"],
            list_process_route_operations: ["config", "process_route_id"],
            get_work_order_release_snapshot: ["config", "work_order_id"],
        }
        for helper, parameter_names in expected.items():
            with self.subTest(helper=helper.__name__):
                self.assertEqual(
                    list(inspect.signature(helper).parameters),
                    parameter_names,
                )

    def test_work_order_release_read_sql_is_explicit_parameterized_and_read_only(self) -> None:
        sql_constants = (
            mesql_v2.SELECT_WORK_ORDER_ROUTE_RELEASE_SQL,
            mesql_v2.SELECT_WORK_ORDER_ROUTE_RELEASE_BY_ID_SQL,
            mesql_v2.SELECT_EXACT_PROCESS_ROUTE_SQL,
            mesql_v2.SELECT_PROCESS_ROUTE_OPERATIONS_SQL,
            mesql_v2.SELECT_WORK_ORDER_RELEASE_WORK_ORDER_SQL,
            mesql_v2.SELECT_WORK_ORDER_RELEASE_OPERATIONS_SQL,
            mesql_v2.SELECT_WORK_ORDER_RELEASE_BINDINGS_SQL,
            mesql_v2.SELECT_WORK_ORDER_RELEASE_INITIAL_QUEUE_SQL,
        )
        for sql in sql_constants:
            lowered = sql.strip().lower()
            with self.subTest(sql=lowered.splitlines()[0]):
                self.assertTrue(lowered.startswith("select"))
                self.assertNotIn("select *", lowered)
                self.assertNotIn("insert into", lowered)
                self.assertNotIn("\nupdate ", lowered)
                self.assertNotIn("delete from", lowered)
                self.assertNotIn("merge into", lowered)
                self.assertNotIn("for update", lowered)
                self.assertIn("%(", lowered)

    def test_release_select_and_mapper_expose_exact_fourteen_fields(self) -> None:
        expected_fields = {
            "release_pk",
            "release_id",
            "order_id",
            "process_route_id",
            "route_code",
            "route_version",
            "release_mode",
            "release_source",
            "released_by",
            "released_at",
            "route_operation_count",
            "operation_set_digest",
            "metadata",
            "created_at",
        }
        for sql in (
            mesql_v2.SELECT_WORK_ORDER_ROUTE_RELEASE_SQL,
            mesql_v2.SELECT_WORK_ORDER_ROUTE_RELEASE_BY_ID_SQL,
        ):
            selected = sql.lower().split("from mes.work_order_route_releases")[0]
            for field in expected_fields:
                self.assertIn(field, selected)
        self.assertEqual(
            set(mesql_v2._work_order_route_release_row(
                _fake_work_order_route_release()
            )),
            expected_fields,
        )

    def test_get_work_order_route_release_reads_exact_order_id(self) -> None:
        connection = _Connection()
        connection.cursor_instance.work_order_route_release_rows = [
            _fake_work_order_route_release(order_id="Order-Case-001")
        ]

        release = self._call_read(
            connection,
            get_work_order_route_release,
            " Order-Case-001 ",
        )

        self.assertEqual(release["order_id"], "Order-Case-001")
        self.assertEqual(
            connection.cursor_instance.last_params,
            {"work_order_id": "Order-Case-001"},
        )

    def test_get_work_order_route_release_by_id_preserves_case(self) -> None:
        connection = _Connection()
        connection.cursor_instance.work_order_route_release_rows = [
            _fake_work_order_route_release(release_id="Release-Case-001")
        ]

        release = self._call_read(
            connection,
            get_work_order_route_release_by_id,
            " Release-Case-001 ",
        )

        self.assertEqual(release["release_id"], "Release-Case-001")
        self.assertEqual(
            connection.cursor_instance.last_params,
            {"release_id": "Release-Case-001"},
        )

    def test_release_mapping_is_json_safe_without_extra_fields(self) -> None:
        connection = _Connection()
        connection.cursor_instance.work_order_route_release_rows = [
            _fake_work_order_route_release(metadata={"uuid": UUID(int=1)})
        ]

        release = self._call_read(
            connection,
            get_work_order_route_release,
            "WO-RELEASE-001",
        )

        self.assertEqual(len(release), 14)
        self.assertEqual(release["metadata"]["uuid"], str(UUID(int=1)))
        self.assertEqual(release["released_at"], "2026-07-15T12:00:00")
        json.dumps(release)

    def test_release_reads_return_none_for_missing_or_case_mismatched_identity(self) -> None:
        connection = _Connection()
        connection.cursor_instance.work_order_route_release_rows = [
            _fake_work_order_route_release(release_id="Release-Case-001")
        ]

        missing = self._call_read(
            connection,
            get_work_order_route_release,
            "WO-MISSING",
        )
        wrong_case = self._call_read(
            connection,
            get_work_order_route_release_by_id,
            "release-case-001",
        )

        self.assertIsNone(missing)
        self.assertIsNone(wrong_case)

    def test_release_read_validation_finishes_before_database_connection(self) -> None:
        cases = (
            (get_work_order_route_release, None, "WORK_ORDER_ID_INVALID"),
            (get_work_order_route_release, " ", "WORK_ORDER_ID_REQUIRED"),
            (get_work_order_route_release_by_id, 7, "RELEASE_ID_INVALID"),
            (get_work_order_route_release_by_id, "", "RELEASE_ID_REQUIRED"),
        )
        for helper, value, expected in cases:
            with self.subTest(helper=helper.__name__, value=value):
                with patch.object(mesql_v2, "database_connection") as factory:
                    with self.assertRaises(mesql_v2.MesqlV2Error) as error:
                        helper(AppConfig(db_enabled=True), value)
                self.assertEqual(error.exception.detail, expected)
                factory.assert_not_called()

    def test_all_release_read_helpers_match_database_disabled_contract(self) -> None:
        calls = (
            (get_work_order_route_release, ("WO-RELEASE-001",)),
            (get_work_order_route_release_by_id, ("RELEASE-001",)),
            (get_exact_process_route, ("ROUTE_BOX_PACKAGING_V2", 2)),
            (list_process_route_operations, ("ROUTE_BOX_PACKAGING_V2",)),
            (get_work_order_release_snapshot, ("WO-RELEASE-001",)),
        )
        for helper, args in calls:
            with self.subTest(helper=helper.__name__):
                with patch.object(
                    mesql_v2,
                    "database_connection",
                    return_value=_yield_connection(None),
                ):
                    with self.assertRaises(mesql_v2.MesqlV2Error) as error:
                        helper(AppConfig(db_enabled=False), *args)
                self.assertEqual(error.exception.detail, "DATABASE_DISABLED")
                self.assertEqual(error.exception.status_code, 503)

    def test_release_read_propagates_database_error_and_cleans_up_cursor(self) -> None:
        connection = _Connection()
        connection.cursor_instance.raise_on_sql_fragment = (
            "from mes.work_order_route_releases"
        )

        with self.assertRaisesRegex(RuntimeError, "forced cursor failure"):
            self._call_read(
                connection,
                get_work_order_route_release,
                "WO-RELEASE-001",
            )

        self.assertTrue(connection.cursor_instance.exited)

    def test_release_read_propagates_missing_table_error(self) -> None:
        connection = _Connection()
        connection.cursor_instance.exception_on_sql_fragment = (
            "from mes.work_order_route_releases",
            UndefinedTable("missing release table"),
        )

        with self.assertRaises(UndefinedTable):
            self._call_read(
                connection,
                get_work_order_route_release,
                "WO-RELEASE-001",
            )

    def test_get_exact_process_route_returns_inactive_exact_version_and_route_id(self) -> None:
        connection = _Connection()
        connection.cursor_instance.process_route_rows = [
            _fake_process_route(
                "ROUTE_BOX_PACKAGING_V2",
                route_id="Route-Identity-V2",
                version=2,
                active=False,
            )
        ]

        route = self._call_read(
            connection,
            get_exact_process_route,
            " route_box_packaging_v2 ",
            2,
        )

        self.assertEqual(route["route_id"], "Route-Identity-V2")
        self.assertEqual(route["route_code"], "ROUTE_BOX_PACKAGING_V2")
        self.assertFalse(route["active"])
        self.assertNotIn("active = true", connection.cursor_instance.last_sql.lower())

    def test_get_exact_process_route_never_substitutes_wrong_version(self) -> None:
        connection = _Connection()
        connection.cursor_instance.process_route_rows = [
            _fake_process_route("ROUTE_BOX_PACKAGING_V2", version=1)
        ]

        route = self._call_read(
            connection,
            get_exact_process_route,
            "ROUTE_BOX_PACKAGING_V2",
            2,
        )

        self.assertIsNone(route)
        self.assertEqual(connection.cursor_instance.last_params["route_version"], 2)
        self.assertNotIn("max(", connection.cursor_instance.last_sql.lower())
        self.assertNotIn("latest", connection.cursor_instance.last_sql.lower())

    def test_get_exact_process_route_rejects_invalid_version_before_database(self) -> None:
        for value, expected in (
            (None, "ROUTE_VERSION_REQUIRED"),
            (0, "ROUTE_VERSION_INVALID"),
            (-1, "ROUTE_VERSION_INVALID"),
            (True, "ROUTE_VERSION_INVALID"),
            (2.0, "ROUTE_VERSION_INVALID"),
            ("2", "ROUTE_VERSION_INVALID"),
        ):
            with self.subTest(value=value):
                with patch.object(mesql_v2, "database_connection") as factory:
                    with self.assertRaises(mesql_v2.MesqlV2Error) as error:
                        get_exact_process_route(
                            AppConfig(db_enabled=True),
                            "ROUTE_BOX_PACKAGING_V2",
                            value,
                        )
                self.assertEqual(error.exception.detail, expected)
                factory.assert_not_called()

    def test_list_process_route_operations_is_deterministically_ordered(self) -> None:
        connection = _Connection()
        cursor = connection.cursor_instance
        cursor.process_route_rows = [
            _fake_process_route(
                "ROUTE_BOX_PACKAGING_V2",
                route_id="Route-Identity-V2",
                version=2,
            )
        ]
        cursor.process_route_operation_rows = [
            _fake_route_operation(
                "Route-Op-B",
                route_code="ROUTE_BOX_PACKAGING_V2",
                route_version=2,
                sequence_no=20,
            ),
            _fake_route_operation(
                "Route-Op-A",
                route_code="ROUTE_BOX_PACKAGING_V2",
                route_version=2,
                sequence_no=10,
                operation_code="Operation-Code-Mixed",
                station_code="Station-Mixed",
            ),
        ]

        operations = self._call_read(
            connection,
            list_process_route_operations,
            " Route-Identity-V2 ",
        )

        self.assertEqual(
            [operation["route_operation_id"] for operation in operations],
            ["Route-Op-A", "Route-Op-B"],
        )
        self.assertEqual(operations[0]["operation_code"], "Operation-Code-Mixed")
        self.assertEqual(operations[0]["station_code"], "Station-Mixed")
        self.assertEqual(cursor.last_params, {"process_route_id": "Route-Identity-V2"})

    def test_list_process_route_operations_returns_empty_list(self) -> None:
        connection = _Connection()

        operations = self._call_read(
            connection,
            list_process_route_operations,
            "MISSING-ROUTE",
        )

        self.assertEqual(operations, [])

    def test_list_process_route_operations_validates_identity_before_database(self) -> None:
        for value, expected in (
            (None, "PROCESS_ROUTE_ID_INVALID"),
            (" ", "PROCESS_ROUTE_ID_REQUIRED"),
        ):
            with self.subTest(value=value):
                with patch.object(mesql_v2, "database_connection") as factory:
                    with self.assertRaises(mesql_v2.MesqlV2Error) as error:
                        list_process_route_operations(
                            AppConfig(db_enabled=True),
                            value,
                        )
                self.assertEqual(error.exception.detail, expected)
                factory.assert_not_called()

    def test_process_route_operation_sql_uses_exact_identity_join_and_order(self) -> None:
        lowered = mesql_v2.SELECT_PROCESS_ROUTE_OPERATIONS_SQL.lower()
        self.assertIn("join mes.process_routes route", lowered)
        self.assertIn("route.route_code = operation.route_code", lowered)
        self.assertIn("route.version = operation.route_version", lowered)
        self.assertIn("where route.route_id = %(process_route_id)s", lowered)
        self.assertIn(
            "order by operation.sequence_no asc, operation.route_operation_id asc",
            " ".join(lowered.split()),
        )
        self.assertNotIn("active = true", lowered)

    def test_work_order_release_snapshot_returns_exact_full_shape(self) -> None:
        connection = _Connection()
        self._seed_release_snapshot(connection)

        snapshot = self._call_read(
            connection,
            get_work_order_release_snapshot,
            "WO-RELEASE-001",
        )

        self.assertEqual(
            set(snapshot),
            {"release", "work_order", "operations", "bindings", "initial_queue"},
        )
        self.assertEqual(snapshot["work_order"]["order_id"], "WO-RELEASE-001")
        self.assertEqual(
            [operation["sequence_no"] for operation in snapshot["operations"]],
            [10, 20],
        )
        self.assertEqual(len(snapshot["bindings"]), 2)
        self.assertEqual(snapshot["initial_queue"]["station_queue_pk"], 77)

    def test_snapshot_work_order_read_model_has_exact_fixed_fields(self) -> None:
        expected_fields = {
            "order_id",
            "status",
            "product_code",
            "target_quantity",
            "started_at",
            "completed_at",
            "payload",
            "metadata",
        }
        mapped = mesql_v2._work_order_release_work_order_row((
            "WO-RELEASE-001",
            "queued",
            "PACKAGED_PRODUCT",
            Decimal("5.000000"),
            None,
            None,
            {"source": "unit_test"},
            {"released": True},
        ))
        self.assertEqual(set(mapped), expected_fields)
        self.assertEqual(mapped["target_quantity"], 5)
        selected = mesql_v2.SELECT_WORK_ORDER_RELEASE_WORK_ORDER_SQL.lower().split(
            "from mes.work_orders"
        )[0]
        for field in expected_fields:
            self.assertIn(field, selected)
        for excluded in (
            "work_order_pk",
            "erp_type",
            "source_system",
            "source_file",
            "external_ref",
            "created_at",
            "updated_at",
        ):
            self.assertNotIn(excluded, selected)
            self.assertNotIn(excluded, mapped)

    def test_snapshot_lifecycle_operation_read_model_has_exact_fixed_fields(self) -> None:
        expected_fields = {
            "work_order_operation_id",
            "order_id",
            "operation_no",
            "operation_code",
            "operation_name",
            "station_code",
            "status",
            "planned_quantity",
            "good_quantity",
            "scrap_quantity",
            "uom_code",
            "started_at",
            "completed_at",
            "sequence_no",
        }
        mapped = mesql_v2._work_order_release_operation_row((
            UUID("5258d822-55bd-56b1-81ba-7f89193ba4eb"),
            "WO-RELEASE-001",
            10,
            "Operation-Code-Mixed",
            "Operation Name",
            "Station-Mixed",
            "queued",
            Decimal("5.000000"),
            Decimal("0.000000"),
            Decimal("0.000000"),
            "piece",
            None,
            None,
            10,
        ))
        self.assertEqual(set(mapped), expected_fields)
        self.assertEqual(
            mapped["work_order_operation_id"],
            "5258d822-55bd-56b1-81ba-7f89193ba4eb",
        )
        self.assertEqual(mapped["operation_code"], "Operation-Code-Mixed")
        self.assertEqual(mapped["station_code"], "Station-Mixed")
        selected = mesql_v2.SELECT_WORK_ORDER_RELEASE_OPERATIONS_SQL.lower().split(
            "from mes.work_order_operations"
        )[0]
        for field in expected_fields:
            self.assertIn(field, selected)
        for excluded in (
            "mesql_work_order_operation_id",
            "payload",
            "metadata",
            "created_at",
            "updated_at",
        ):
            self.assertNotIn(excluded, selected)
            self.assertNotIn(excluded, mapped)

    def test_snapshot_bindings_follow_lifecycle_operation_order(self) -> None:
        connection = _Connection()
        self._seed_release_snapshot(connection)

        snapshot = self._call_read(
            connection,
            get_work_order_release_snapshot,
            "WO-RELEASE-001",
        )

        self.assertEqual(
            [binding["route_operation_id"] for binding in snapshot["bindings"]],
            ["ROUTE_BOX_PACKAGING_V2_OP10", "ROUTE_BOX_PACKAGING_V2_OP20"],
        )
        normalized_sql = " ".join(
            mesql_v2.SELECT_WORK_ORDER_RELEASE_BINDINGS_SQL.lower().split()
        )
        self.assertIn(
            "order by operation.sequence_no asc, binding.work_order_operation_id asc, binding.binding_id asc",
            normalized_sql,
        )

    def test_work_order_release_snapshot_uses_one_connection_and_cursor_scope(self) -> None:
        connection = _Connection()
        self._seed_release_snapshot(connection)

        with patch.object(
            mesql_v2,
            "database_connection",
            return_value=_yield_connection(connection),
        ) as factory:
            snapshot = get_work_order_release_snapshot(
                AppConfig(db_enabled=True),
                "WO-RELEASE-001",
            )

        self.assertIsNotNone(snapshot)
        factory.assert_called_once()
        self.assertTrue(connection.cursor_instance.exited)
        self.assertEqual(len(connection.cursor_instance.executed), 5)

    def test_work_order_release_snapshot_missing_release_stops_after_first_read(self) -> None:
        connection = _Connection()

        snapshot = self._call_read(
            connection,
            get_work_order_release_snapshot,
            "WO-MISSING",
        )

        self.assertIsNone(snapshot)
        self.assertEqual(len(connection.cursor_instance.executed), 1)

    def test_work_order_release_snapshot_retains_missing_components(self) -> None:
        connection = _Connection()
        connection.cursor_instance.work_order_route_release_rows = [
            _fake_work_order_route_release()
        ]

        snapshot = self._call_read(
            connection,
            get_work_order_release_snapshot,
            "WO-RELEASE-001",
        )

        self.assertIsNone(snapshot["work_order"])
        self.assertEqual(snapshot["operations"], [])
        self.assertEqual(snapshot["bindings"], [])
        self.assertIsNone(snapshot["initial_queue"])

    def test_snapshot_bindings_are_limited_to_work_order_operation_uuids(self) -> None:
        connection = _Connection()
        self._seed_release_snapshot(connection)
        connection.cursor_instance.release_binding_rows.append(
            _fake_work_order_operation_route_binding(
                binding_pk=999,
                binding_id="BINDING-OTHER-WORK-ORDER",
                work_order_operation_id=UUID(
                    "99999999-9999-4999-8999-999999999999"
                ),
            )
        )

        snapshot = self._call_read(
            connection,
            get_work_order_release_snapshot,
            "WO-RELEASE-001",
        )

        self.assertEqual(len(snapshot["bindings"]), 2)
        self.assertNotIn(
            "BINDING-OTHER-WORK-ORDER",
            [binding["binding_id"] for binding in snapshot["bindings"]],
        )
        binding_sql = next(
            sql
            for sql, _params in connection.cursor_instance.executed
            if "from mes.work_order_operation_route_bindings binding" in sql.lower()
        )
        self.assertIn(
            "operation.work_order_operation_id = binding.work_order_operation_id",
            binding_sql.lower(),
        )

    def test_snapshot_initial_queue_is_tied_to_first_ordered_operation_uuid(self) -> None:
        connection = _Connection()
        self._seed_release_snapshot(connection)

        snapshot = self._call_read(
            connection,
            get_work_order_release_snapshot,
            "WO-RELEASE-001",
        )

        queue_params = connection.cursor_instance.executed[-1][1]
        self.assertEqual(
            queue_params["work_order_operation_id"],
            "5258d822-55bd-56b1-81ba-7f89193ba4eb",
        )
        self.assertEqual(queue_params["station_code"], "ASSEMBLY_01")
        self.assertEqual(
            snapshot["initial_queue"]["work_order_operation_id"],
            "5258d822-55bd-56b1-81ba-7f89193ba4eb",
        )

    def test_work_order_release_snapshot_does_not_commit_or_write(self) -> None:
        connection = _Connection()
        self._seed_release_snapshot(connection)

        self._call_read(
            connection,
            get_work_order_release_snapshot,
            "WO-RELEASE-001",
        )

        self.assertFalse(connection.committed)
        for sql, _params in connection.cursor_instance.executed:
            lowered = sql.lower()
            self.assertTrue(lowered.strip().startswith("select"))
            self.assertNotIn("for update", lowered)

    def test_work_order_release_namespace_literals_recompute_from_labels(self) -> None:
        self.assertEqual(
            mesql_v2.WORK_ORDER_RELEASE_OPERATION_NAMESPACE,
            mesql_v2.uuid.uuid5(
                mesql_v2.uuid.NAMESPACE_URL,
                mesql_v2.WORK_ORDER_RELEASE_OPERATION_NAMESPACE_LABEL,
            ),
        )
        self.assertEqual(
            mesql_v2.WORK_ORDER_RELEASE_BINDING_NAMESPACE,
            mesql_v2.uuid.uuid5(
                mesql_v2.uuid.NAMESPACE_URL,
                mesql_v2.WORK_ORDER_RELEASE_BINDING_NAMESPACE_LABEL,
            ),
        )

    def test_operation_uuid_fixed_examples(self) -> None:
        self.assertEqual(
            mesql_v2._derive_work_order_release_operation_id(
                "RELEASE-V2-EXAMPLE-001",
                "ROUTE_BOX_PACKAGING_V2_OP10",
            ),
            "5258d822-55bd-56b1-81ba-7f89193ba4eb",
        )
        self.assertEqual(
            mesql_v2._derive_work_order_release_operation_id(
                "RELEASE-V2-EXAMPLE-001",
                "ROUTE_BOX_PACKAGING_V2_OP20",
            ),
            "26c50f67-2519-5e29-a958-e39eca44934e",
        )

    def test_binding_id_fixed_examples(self) -> None:
        self.assertEqual(
            mesql_v2._derive_work_order_release_binding_id(
                "RELEASE-V2-EXAMPLE-001",
                "ROUTE_BOX_PACKAGING_V2_OP10",
            ),
            "BINDING-WORK-ORDER-RELEASE-AD8E94BA-E408-59B5-BE90-B7F348C17050",
        )
        self.assertEqual(
            mesql_v2._derive_work_order_release_binding_id(
                "RELEASE-V2-EXAMPLE-001",
                "ROUTE_BOX_PACKAGING_V2_OP20",
            ),
            "BINDING-WORK-ORDER-RELEASE-B342D41D-6777-5999-A07E-CE10E04533CA",
        )

    def test_canonical_name_contains_exactly_one_lf_separator(self) -> None:
        canonical = mesql_v2._work_order_release_canonical_name(
            "RELEASE-V2-EXAMPLE-001",
            "ROUTE_BOX_PACKAGING_V2_OP10",
        )

        self.assertEqual(
            canonical,
            "RELEASE-V2-EXAMPLE-001\nROUTE_BOX_PACKAGING_V2_OP10",
        )
        self.assertEqual(canonical.encode("utf-8").count(b"\x0a"), 1)
        self.assertFalse(canonical.endswith("\n"))

    def test_platform_and_backslash_newlines_produce_different_identity(self) -> None:
        expected = mesql_v2._derive_work_order_release_operation_id(
            "RELEASE-V2-EXAMPLE-001",
            "ROUTE_BOX_PACKAGING_V2_OP10",
        )
        platform_name = (
            "RELEASE-V2-EXAMPLE-001\r\nROUTE_BOX_PACKAGING_V2_OP10"
        )
        escaped_name = (
            "RELEASE-V2-EXAMPLE-001\\nROUTE_BOX_PACKAGING_V2_OP10"
        )

        self.assertNotEqual(
            expected,
            str(mesql_v2.uuid.uuid5(
                mesql_v2.WORK_ORDER_RELEASE_OPERATION_NAMESPACE,
                platform_name,
            )),
        )
        self.assertNotEqual(
            expected,
            str(mesql_v2.uuid.uuid5(
                mesql_v2.WORK_ORDER_RELEASE_OPERATION_NAMESPACE,
                escaped_name,
            )),
        )

    def test_identity_inputs_are_trimmed_without_case_normalization(self) -> None:
        canonical = mesql_v2._work_order_release_canonical_name(
            " Release-Mixed ",
            " Route-Operation-Mixed ",
        )
        self.assertEqual(canonical, "Release-Mixed\nRoute-Operation-Mixed")
        self.assertNotEqual(
            mesql_v2._derive_work_order_release_operation_id(
                "Release-Mixed",
                "Route-Operation-Mixed",
            ),
            mesql_v2._derive_work_order_release_operation_id(
                "release-mixed",
                "route-operation-mixed",
            ),
        )

    def test_operation_set_digest_matches_fixed_example(self) -> None:
        digest = mesql_v2._compute_work_order_release_operation_set_digest(
            process_route_id="ROUTE_BOX_PACKAGING_V2",
            route_code="ROUTE_BOX_PACKAGING_V2",
            route_version=2,
            release_mode="route_generated",
            pairs=self._release_pairs(),
        )
        self.assertEqual(
            digest,
            "4063a5c72fd4d38f11757a4bf1115f83e1c05e8b97624deb808193c5d0fcb2e2",
        )
        self.assertRegex(digest, r"^[0-9a-f]{64}$")

    def test_operation_set_digest_is_independent_of_pair_input_order(self) -> None:
        pairs = self._release_pairs()
        kwargs = {
            "process_route_id": "ROUTE_BOX_PACKAGING_V2",
            "route_code": "ROUTE_BOX_PACKAGING_V2",
            "route_version": 2,
            "release_mode": "route_generated",
        }
        forward = mesql_v2._compute_work_order_release_operation_set_digest(
            pairs=pairs,
            **kwargs,
        )
        reverse = mesql_v2._compute_work_order_release_operation_set_digest(
            pairs=list(reversed(pairs)),
            **kwargs,
        )
        self.assertEqual(forward, reverse)

    def test_operation_set_digest_serializes_exact_canonical_payload(self) -> None:
        real_dumps = json.dumps
        with patch.object(
            mesql_v2.json,
            "dumps",
            wraps=real_dumps,
        ) as dumps:
            mesql_v2._compute_work_order_release_operation_set_digest(
                process_route_id="ROUTE_BOX_PACKAGING_V2",
                route_code="ROUTE_BOX_PACKAGING_V2",
                route_version=2,
                release_mode="route_generated",
                pairs=list(reversed(self._release_pairs())),
            )

        payload = dumps.call_args.args[0]
        kwargs = dumps.call_args.kwargs
        serialized = real_dumps(payload, **kwargs)
        self.assertEqual(kwargs, {
            "ensure_ascii": False,
            "sort_keys": True,
            "separators": (",", ":"),
        })
        self.assertEqual(
            serialized,
            '{"pairs":[{"route_operation_id":"ROUTE_BOX_PACKAGING_V2_OP10",'
            '"sequence_no":10,"work_order_operation_id":'
            '"5258d822-55bd-56b1-81ba-7f89193ba4eb"},{"route_operation_id":'
            '"ROUTE_BOX_PACKAGING_V2_OP20","sequence_no":20,'
            '"work_order_operation_id":"26c50f67-2519-5e29-a958-e39eca44934e"}],'
            '"process_route_id":"ROUTE_BOX_PACKAGING_V2",'
            '"release_mode":"route_generated","route_code":'
            '"ROUTE_BOX_PACKAGING_V2","route_version":2}',
        )

    def test_operation_set_digest_rejects_duplicate_sequence(self) -> None:
        pairs = self._release_pairs()
        pairs[1]["sequence_no"] = 10
        with self.assertRaises(mesql_v2.MesqlV2Error) as error:
            mesql_v2._compute_work_order_release_operation_set_digest(
                process_route_id="ROUTE_BOX_PACKAGING_V2",
                route_code="ROUTE_BOX_PACKAGING_V2",
                route_version=2,
                release_mode="route_generated",
                pairs=pairs,
            )
        self.assertEqual(error.exception.detail, "SEQUENCE_NO_INVALID")

    def test_operation_set_digest_rejects_duplicate_route_operation(self) -> None:
        pairs = self._release_pairs()
        pairs[1]["route_operation_id"] = pairs[0]["route_operation_id"]
        with self.assertRaises(mesql_v2.MesqlV2Error) as error:
            mesql_v2._compute_work_order_release_operation_set_digest(
                process_route_id="ROUTE_BOX_PACKAGING_V2",
                route_code="ROUTE_BOX_PACKAGING_V2",
                route_version=2,
                release_mode="route_generated",
                pairs=pairs,
            )
        self.assertEqual(error.exception.detail, "ROUTE_OPERATION_ID_INVALID")

    def test_operation_set_digest_rejects_duplicate_lifecycle_uuid(self) -> None:
        pairs = self._release_pairs()
        pairs[1]["work_order_operation_id"] = pairs[0]["work_order_operation_id"]
        with self.assertRaises(mesql_v2.MesqlV2Error) as error:
            mesql_v2._compute_work_order_release_operation_set_digest(
                process_route_id="ROUTE_BOX_PACKAGING_V2",
                route_code="ROUTE_BOX_PACKAGING_V2",
                route_version=2,
                release_mode="route_generated",
                pairs=pairs,
            )
        self.assertEqual(error.exception.detail, "WORK_ORDER_OPERATION_ID_INVALID")

    def test_operation_set_digest_rejects_bool_version_and_sequence(self) -> None:
        for field, value, expected in (
            ("route_version", True, "ROUTE_VERSION_INVALID"),
            ("sequence_no", True, "SEQUENCE_NO_INVALID"),
        ):
            pairs = self._release_pairs()
            kwargs = {
                "process_route_id": "ROUTE_BOX_PACKAGING_V2",
                "route_code": "ROUTE_BOX_PACKAGING_V2",
                "route_version": 2,
                "release_mode": "route_generated",
                "pairs": pairs,
            }
            if field == "sequence_no":
                pairs[0]["sequence_no"] = value
            else:
                kwargs[field] = value
            with self.subTest(field=field):
                with self.assertRaises(mesql_v2.MesqlV2Error) as error:
                    mesql_v2._compute_work_order_release_operation_set_digest(**kwargs)
                self.assertEqual(error.exception.detail, expected)

    def test_operation_set_digest_rejects_empty_or_invalid_pair_shape(self) -> None:
        base = {
            "process_route_id": "ROUTE_BOX_PACKAGING_V2",
            "route_code": "ROUTE_BOX_PACKAGING_V2",
            "route_version": 2,
            "release_mode": "route_generated",
        }
        for pairs, expected in (
            (None, "OPERATION_SET_REQUIRED"),
            ([], "OPERATION_SET_REQUIRED"),
            ((), "OPERATION_SET_INVALID"),
            ([{"sequence_no": 10}], "OPERATION_SET_INVALID"),
            ([{**self._release_pairs()[0], "metadata": {}}], "OPERATION_SET_INVALID"),
        ):
            with self.subTest(pairs=pairs):
                with self.assertRaises(mesql_v2.MesqlV2Error) as error:
                    mesql_v2._compute_work_order_release_operation_set_digest(
                        pairs=pairs,
                        **base,
                    )
                self.assertEqual(error.exception.detail, expected)

    def test_operation_set_digest_validates_required_scalar_fields(self) -> None:
        base = {
            "process_route_id": "ROUTE_BOX_PACKAGING_V2",
            "route_code": "ROUTE_BOX_PACKAGING_V2",
            "route_version": 2,
            "release_mode": "route_generated",
            "pairs": self._release_pairs(),
        }
        for field, value, expected in (
            ("process_route_id", " ", "PROCESS_ROUTE_ID_REQUIRED"),
            ("route_code", None, "ROUTE_CODE_INVALID"),
            ("route_version", 0, "ROUTE_VERSION_INVALID"),
            ("release_mode", "", "RELEASE_MODE_REQUIRED"),
        ):
            kwargs = dict(base)
            kwargs[field] = value
            with self.subTest(field=field):
                with self.assertRaises(mesql_v2.MesqlV2Error) as error:
                    mesql_v2._compute_work_order_release_operation_set_digest(**kwargs)
                self.assertEqual(error.exception.detail, expected)

    def test_operation_set_digest_requires_canonical_lowercase_uuid_text(self) -> None:
        pairs = self._release_pairs()
        pairs[0]["work_order_operation_id"] = pairs[0][
            "work_order_operation_id"
        ].upper()
        with self.assertRaises(mesql_v2.MesqlV2Error) as error:
            mesql_v2._compute_work_order_release_operation_set_digest(
                process_route_id="ROUTE_BOX_PACKAGING_V2",
                route_code="ROUTE_BOX_PACKAGING_V2",
                route_version=2,
                release_mode="route_generated",
                pairs=pairs,
            )
        self.assertEqual(error.exception.detail, "WORK_ORDER_OPERATION_ID_INVALID")

    def test_operation_set_digest_rejects_unsupported_release_mode(self) -> None:
        with self.assertRaises(mesql_v2.MesqlV2Error) as error:
            mesql_v2._compute_work_order_release_operation_set_digest(
                process_route_id="ROUTE_BOX_PACKAGING_V2",
                route_code="ROUTE_BOX_PACKAGING_V2",
                route_version=2,
                release_mode="legacy_generated",
                pairs=self._release_pairs(),
            )
        self.assertEqual(error.exception.detail, "RELEASE_MODE_INVALID")

    def test_digest_signature_excludes_release_and_audit_fields(self) -> None:
        parameters = inspect.signature(
            mesql_v2._compute_work_order_release_operation_set_digest
        ).parameters
        self.assertEqual(
            set(parameters),
            {"process_route_id", "route_code", "route_version", "release_mode", "pairs"},
        )
        for excluded in (
            "release_id",
            "metadata",
            "released_by",
            "release_source",
            "released_at",
        ):
            self.assertNotIn(excluded, parameters)


class _ReleasePrimitiveCursor:
    def __init__(self, responses: list[tuple[str, object]]) -> None:
        self.responses = list(responses)
        self.executed: list[tuple[str, dict]] = []
        self.current: tuple[str, object] | None = None

    def execute(self, sql: str, params: dict | None = None) -> None:
        self.executed.append((sql, params or {}))
        self.current = self.responses.pop(0) if self.responses else ("one", None)

    def fetchone(self):
        assert self.current is not None
        kind, value = self.current
        assert kind == "one"
        return value

    def fetchall(self):
        assert self.current is not None
        kind, value = self.current
        assert kind == "all"
        return value


class WorkOrderReleasePrimitiveTests(unittest.TestCase):
    release_id = "RELEASE-100"
    operation_id = "13be7645-ea17-5260-8943-52a953399bb7"

    def _route(self, **overrides):
        value = {
            "route_id": "ROUTE-ID-2", "route_code": "ROUTE-2", "version": 2,
            "route_name": "Route 2", "item_code": "ITEM-1", "active": True,
            "metadata": {},
        }
        value.update(overrides)
        return value

    def _item(self, **overrides):
        value = {
            "item_code": "ITEM-1", "item_name": "Item", "item_type": "product",
            "unit": "EA", "active": True, "metadata": {},
        }
        value.update(overrides)
        return value

    def _route_operations(self):
        return [
            {
                "route_operation_id": "ROP-20", "sequence_no": 20,
                "route_code": "ROUTE-2", "route_version": 2,
                "operation_code": "OP-20", "operation_name": "Second",
                "station_code": "ST-2", "active": True,
            },
            {
                "route_operation_id": "ROP-10", "sequence_no": 10,
                "route_code": "ROUTE-2", "route_version": 2,
                "operation_code": "OP-10", "operation_name": "First",
                "station_code": "ST-1", "active": True,
            },
        ]

    def _operation_snapshots(self):
        return mesql_v2._build_route_generated_operation_snapshots(
            release_id=self.release_id,
            work_order_id="WO-1",
            process_route=self._route(),
            route_item=self._item(),
            route_operations=self._route_operations(),
            target_quantity=Decimal("4.5"),
        )

    def _work_order(self, **overrides):
        value = {
            "order_id": "WO-1", "status": "planned", "product_code": "ITEM-1",
            "target_quantity": 5, "started_at": None, "completed_at": None,
        }
        value.update(overrides)
        return value

    def test_operation_builder_orders_by_sequence(self) -> None:
        snapshots = self._operation_snapshots()
        self.assertEqual([item["sequence_no"] for item in snapshots], [10, 20])

    def test_operation_builder_sets_only_first_queued(self) -> None:
        self.assertEqual(
            [item["status"] for item in self._operation_snapshots()],
            ["queued", "planned"],
        )

    def test_operation_builder_sets_exact_server_metadata(self) -> None:
        metadata = self._operation_snapshots()[0]["metadata"]
        self.assertEqual(set(metadata), {
            "source", "release_id", "process_route_id", "route_code",
            "route_version", "route_operation_id",
        })

    def test_operation_builder_uses_route_item_unit(self) -> None:
        self.assertEqual(self._operation_snapshots()[0]["uom_code"], "EA")

    def test_operation_builder_has_null_mesql_and_timestamps(self) -> None:
        operation = self._operation_snapshots()[0]
        self.assertIsNone(operation["mesql_work_order_operation_id"])
        self.assertIsNone(operation["started_at"])
        self.assertIsNone(operation["completed_at"])

    def test_operation_builder_uses_deterministic_uuid(self) -> None:
        operation = self._operation_snapshots()[0]
        self.assertEqual(
            operation["work_order_operation_id"],
            mesql_v2._derive_work_order_release_operation_id(
                self.release_id, "ROP-10"
            ),
        )

    def test_binding_builder_uses_fixed_derivation_contract(self) -> None:
        bindings = mesql_v2._build_work_order_release_binding_snapshots(
            release_id=self.release_id,
            released_by="planner",
            route_operations=self._route_operations(),
            operation_snapshots=self._operation_snapshots(),
        )
        self.assertEqual(
            bindings[0]["binding_id"],
            mesql_v2._derive_work_order_release_binding_id(
                self.release_id, "ROP-10"
            ),
        )

    def test_binding_builder_has_exact_metadata(self) -> None:
        bindings = mesql_v2._build_work_order_release_binding_snapshots(
            release_id=self.release_id, released_by="planner",
            route_operations=self._route_operations(),
            operation_snapshots=self._operation_snapshots(),
        )
        self.assertEqual(bindings[0]["metadata"], {"release_id": self.release_id})

    def test_binding_builder_rejects_count_mismatch(self) -> None:
        with self.assertRaisesRegex(mesql_v2.MesqlV2Error, "COUNT_MISMATCH"):
            mesql_v2._build_work_order_release_binding_snapshots(
                release_id=self.release_id, released_by="planner",
                route_operations=self._route_operations()[:1],
                operation_snapshots=self._operation_snapshots(),
            )

    def test_binding_builder_rejects_tampered_lifecycle_uuid(self) -> None:
        operations = self._operation_snapshots()
        operations[0]["work_order_operation_id"] = self.operation_id
        with self.assertRaisesRegex(mesql_v2.MesqlV2Error, "MAPPING_CONFLICT"):
            mesql_v2._build_work_order_release_binding_snapshots(
                release_id=self.release_id, released_by="planner",
                route_operations=self._route_operations(),
                operation_snapshots=operations,
            )

    def test_queue_builder_has_no_route_config_identity(self) -> None:
        queue = mesql_v2._build_initial_queue_snapshot(
            release_id=self.release_id,
            operation_snapshot=self._operation_snapshots()[0], queue_rank=3,
        )
        serialized = json.dumps(queue)
        self.assertNotIn("route_operation_id", serialized)
        self.assertNotIn("process_route_id", serialized)

    def test_queue_builder_payload_is_exact(self) -> None:
        operation = self._operation_snapshots()[0]
        queue = mesql_v2._build_initial_queue_snapshot(
            release_id=self.release_id, operation_snapshot=operation, queue_rank=3,
        )
        self.assertEqual(set(queue["payload"]), {
            "order_id", "work_order_operation_id", "operation_no", "sequence_no",
            "station_code", "status",
        })

    def test_queue_builder_rejects_negative_rank(self) -> None:
        with self.assertRaisesRegex(mesql_v2.MesqlV2Error, "QUEUE_CONFLICT"):
            mesql_v2._build_initial_queue_snapshot(
                release_id=self.release_id,
                operation_snapshot=self._operation_snapshots()[0], queue_rank=-1,
            )

    def test_config_rejects_missing_route(self) -> None:
        with self.assertRaises(mesql_v2.MesqlV2Error) as error:
            mesql_v2._validate_route_generated_config(None, self._item(), [])
        self.assertEqual(error.exception.status_code, 404)

    def test_config_rejects_empty_operations(self) -> None:
        with self.assertRaises(mesql_v2.MesqlV2Error) as error:
            mesql_v2._validate_route_generated_config(self._route(), self._item(), [])
        self.assertEqual(error.exception.detail, "ROUTE_OPERATION_NOT_FOUND")

    def test_config_rejects_inactive_route(self) -> None:
        with self.assertRaisesRegex(mesql_v2.MesqlV2Error, "NOT_RELEASABLE"):
            mesql_v2._validate_route_generated_config(
                self._route(active=False), self._item(), self._route_operations()
            )

    def test_config_rejects_inactive_item(self) -> None:
        with self.assertRaisesRegex(mesql_v2.MesqlV2Error, "NOT_RELEASABLE"):
            mesql_v2._validate_route_generated_config(
                self._route(), self._item(active=False), self._route_operations()
            )

    def test_config_rejects_blank_unit(self) -> None:
        with self.assertRaisesRegex(mesql_v2.MesqlV2Error, "NOT_RELEASABLE"):
            mesql_v2._validate_route_generated_config(
                self._route(), self._item(unit=" "), self._route_operations()
            )

    def test_config_rejects_duplicate_sequence(self) -> None:
        operations = self._route_operations()
        operations[1]["sequence_no"] = 20
        with self.assertRaisesRegex(mesql_v2.MesqlV2Error, "NOT_RELEASABLE"):
            mesql_v2._validate_route_generated_config(
                self._route(), self._item(), operations
            )

    def test_config_rejects_cross_version_operation(self) -> None:
        operations = self._route_operations()
        operations[0]["route_version"] = 3
        with self.assertRaisesRegex(mesql_v2.MesqlV2Error, "NOT_RELEASABLE"):
            mesql_v2._validate_route_generated_config(
                self._route(), self._item(), operations
            )

    def test_eligibility_accepts_clean_planned_work_order(self) -> None:
        mesql_v2._validate_route_generated_release_eligibility(
            work_order=self._work_order(), process_route=self._route(),
            route_item=self._item(), route_operations=self._route_operations(),
            existing_operations=[], existing_bindings=[], existing_queue=[], evidence={},
        )

    def test_eligibility_accepts_structurally_clean_queued_work_order(self) -> None:
        mesql_v2._validate_route_generated_release_eligibility(
            work_order=self._work_order(status="queued"), process_route=self._route(),
            route_item=self._item(), route_operations=self._route_operations(),
            existing_operations=[], existing_bindings=[], existing_queue=[], evidence={},
        )

    def test_eligibility_compares_normalized_product_codes(self) -> None:
        mesql_v2._validate_route_generated_release_eligibility(
            work_order=self._work_order(product_code="item-1"),
            process_route=self._route(item_code="ITEM-1"),
            route_item=self._item(item_code="Item-1"),
            route_operations=self._route_operations(), existing_operations=[],
            existing_bindings=[], existing_queue=[], evidence={},
        )

    def test_eligibility_rejects_nonpositive_target(self) -> None:
        with self.assertRaisesRegex(mesql_v2.MesqlV2Error, "NOT_RELEASABLE"):
            mesql_v2._validate_route_generated_release_eligibility(
                work_order=self._work_order(target_quantity=0),
                process_route=self._route(), route_item=self._item(),
                route_operations=self._route_operations(), existing_operations=[],
                existing_bindings=[], existing_queue=[], evidence={},
            )

    def test_eligibility_rejects_product_mismatch(self) -> None:
        with self.assertRaisesRegex(mesql_v2.MesqlV2Error, "NOT_RELEASABLE"):
            mesql_v2._validate_route_generated_release_eligibility(
                work_order=self._work_order(product_code="OTHER"),
                process_route=self._route(), route_item=self._item(),
                route_operations=self._route_operations(), existing_operations=[],
                existing_bindings=[], existing_queue=[], evidence={},
            )

    def test_eligibility_rejects_runtime_evidence(self) -> None:
        with self.assertRaisesRegex(mesql_v2.MesqlV2Error, "NOT_RELEASABLE"):
            mesql_v2._validate_route_generated_release_eligibility(
                work_order=self._work_order(), process_route=self._route(),
                route_item=self._item(), route_operations=self._route_operations(),
                existing_operations=[], existing_bindings=[], existing_queue=[],
                evidence={"operation_event_count": 1},
            )

    def test_release_comparator_ignores_database_timestamps(self) -> None:
        expected = {name: name for name in (
            "release_id", "order_id", "process_route_id", "route_code",
            "route_version", "release_mode", "release_source", "released_by",
            "route_operation_count", "operation_set_digest", "metadata",
        )}
        persisted = {**expected, "released_at": "later", "created_at": "later"}
        self.assertTrue(mesql_v2._compare_immutable_release_request(persisted, expected))

    def test_operation_comparator_ignores_mutable_operational_state(self) -> None:
        expected = self._operation_snapshots()
        persisted = deepcopy(expected)
        persisted[0].update({
            "status": "completed", "good_quantity": 4.5, "scrap_quantity": 1,
            "started_at": "2026-01-01", "completed_at": "2026-01-02",
            "updated_at": "2026-01-03",
        })
        self.assertTrue(
            mesql_v2._compare_static_operation_snapshots(persisted, expected)
        )

    def test_operation_comparator_detects_static_change(self) -> None:
        expected = self._operation_snapshots()
        persisted = deepcopy(expected)
        persisted[0]["station_code"] = "OTHER"
        self.assertFalse(
            mesql_v2._compare_static_operation_snapshots(persisted, expected)
        )

    def test_binding_comparator_detects_missing_binding(self) -> None:
        self.assertFalse(mesql_v2._compare_complete_binding_set([], [{"binding_id": "B"}]))

    def test_queue_comparator_ignores_status_rank_and_timestamps(self) -> None:
        expected = mesql_v2._build_initial_queue_snapshot(
            release_id=self.release_id,
            operation_snapshot=self._operation_snapshots()[0], queue_rank=0,
        )
        persisted = {**expected, "status": "completed", "queue_rank": 99,
                     "created_at": "a", "updated_at": "b"}
        self.assertTrue(mesql_v2._compare_initial_queue_identity(persisted, expected))

    def test_queue_comparator_detects_lifecycle_change(self) -> None:
        expected = mesql_v2._build_initial_queue_snapshot(
            release_id=self.release_id,
            operation_snapshot=self._operation_snapshots()[0], queue_rank=0,
        )
        persisted = {**expected, "work_order_operation_id": self.operation_id}
        self.assertFalse(mesql_v2._compare_initial_queue_identity(persisted, expected))

    def test_queue_lock_uses_three_statements_and_returns_rank(self) -> None:
        cursor = _ReleasePrimitiveCursor([
            ("one", (None,)), ("all", []), ("one", (7,)),
        ])
        result = mesql_v2._lock_station_queue_scope_cursor(cursor, "ST-1")
        self.assertEqual(result["next_queue_rank"], 7)
        self.assertEqual(len(cursor.executed), 3)

    def test_queue_rank_sql_excludes_ready(self) -> None:
        sql = mesql_v2.SELECT_NEXT_STATION_QUEUE_RANK_CURSOR_SQL.lower()
        self.assertIn("'queued', 'active', 'pending_approval'", sql)
        self.assertNotIn("ready", sql)

    def test_read_snapshot_missing_release_has_stable_shape(self) -> None:
        cursor = _ReleasePrimitiveCursor([("one", None)])
        snapshot = mesql_v2._read_work_order_release_snapshot_cursor(cursor, "WO-X")
        self.assertEqual(snapshot["operations"], [])
        self.assertIsNone(snapshot["release"])
        self.assertEqual(set(snapshot), {
            "release", "work_order", "operations", "bindings", "initial_queue"
        })

    def test_snapshot_cursor_reuses_phase_5c_shape_unchanged(self) -> None:
        expected = {
            "release": {"release_id": "R"}, "work_order": {"order_id": "WO"},
            "operations": [{"sequence_no": 10}], "bindings": [],
            "initial_queue": None,
        }
        with patch.object(
            mesql_v2, "_get_work_order_release_snapshot_with_cursor",
            return_value=expected,
        ) as reader:
            self.assertIs(
                mesql_v2._read_work_order_release_snapshot_cursor(object(), "WO"),
                expected,
            )
        reader.assert_called_once()

    def _invariant_fixture(self, released=False):
        release = {
            "release_id": self.release_id, "order_id": "WO-1",
            "process_route_id": "ROUTE-ID-2", "route_code": "ROUTE-2",
            "route_version": 2, "release_mode": "route_generated",
            "release_source": "local_planning", "released_by": "planner",
            "route_operation_count": 2, "operation_set_digest": "",
            "metadata": {},
        }
        operations = self._operation_snapshots()
        bindings = mesql_v2._build_work_order_release_binding_snapshots(
            release_id=self.release_id, released_by="planner",
            route_operations=self._route_operations(), operation_snapshots=operations,
        )
        binding_by_operation = {
            binding["work_order_operation_id"]: binding for binding in bindings
        }
        release["operation_set_digest"] = (
            mesql_v2._compute_work_order_release_operation_set_digest(
                process_route_id=release["process_route_id"],
                route_code=release["route_code"],
                route_version=release["route_version"],
                release_mode=release["release_mode"],
                pairs=[
                    {
                        "sequence_no": operation["sequence_no"],
                        "route_operation_id": binding_by_operation[
                            operation["work_order_operation_id"]
                        ]["route_operation_id"],
                        "work_order_operation_id": operation[
                            "work_order_operation_id"
                        ],
                    }
                    for operation in operations
                ],
            )
        )
        queue = mesql_v2._build_initial_queue_snapshot(
            release_id=self.release_id, operation_snapshot=operations[0], queue_rank=2,
        )
        return {
            "work_order_id": "WO-1", "release": release, "operations": operations,
            "bindings": bindings, "initial_queue": queue, "released": released,
        }

    def test_invariant_replay_ignores_mutable_progression(self) -> None:
        expected = self._invariant_fixture(released=False)
        operations = deepcopy(expected["operations"])
        operations[0].update({
            "status": "completed", "good_quantity": 5, "scrap_quantity": 1,
            "started_at": "start", "completed_at": "end",
        })
        queue = {**expected["initial_queue"], "status": "active", "queue_rank": 99}
        with (
            patch.object(mesql_v2, "_get_work_order_route_release_with_cursor", return_value=expected["release"]),
            patch.object(mesql_v2, "_select_work_order_for_release_cursor", return_value={"status": "completed"}),
            patch.object(mesql_v2, "_list_existing_work_order_operations_for_update_cursor", return_value=operations),
            patch.object(mesql_v2, "_list_existing_release_bindings_for_update_cursor", return_value=expected["bindings"]),
            patch.object(mesql_v2, "_select_initial_queue_cursor", return_value=[queue]),
        ):
            persisted = mesql_v2._validate_work_order_release_invariants_cursor(
                object(), expected
            )
        self.assertEqual(persisted["work_order"]["status"], "completed")

    def test_invariant_first_write_rejects_mutable_progression(self) -> None:
        expected = self._invariant_fixture(released=True)
        operations = deepcopy(expected["operations"])
        operations[0]["status"] = "completed"
        with (
            patch.object(mesql_v2, "_get_work_order_route_release_with_cursor", return_value=expected["release"]),
            patch.object(mesql_v2, "_select_work_order_for_release_cursor", return_value={"status": "queued"}),
            patch.object(mesql_v2, "_list_existing_work_order_operations_for_update_cursor", return_value=operations),
            patch.object(mesql_v2, "_list_existing_release_bindings_for_update_cursor", return_value=expected["bindings"]),
            patch.object(mesql_v2, "_select_initial_queue_cursor", return_value=[expected["initial_queue"]]),
        ):
            with self.assertRaisesRegex(mesql_v2.MesqlV2Error, "SNAPSHOT_MISMATCH"):
                mesql_v2._validate_work_order_release_invariants_cursor(object(), expected)

    def test_invariant_selects_queue_for_minimum_sequence_operation(self) -> None:
        expected = self._invariant_fixture(released=False)
        reversed_operations = list(reversed(expected["operations"]))
        with (
            patch.object(mesql_v2, "_get_work_order_route_release_with_cursor", return_value=expected["release"]),
            patch.object(mesql_v2, "_select_work_order_for_release_cursor", return_value={"status": "queued"}),
            patch.object(mesql_v2, "_list_existing_work_order_operations_for_update_cursor", return_value=reversed_operations),
            patch.object(mesql_v2, "_list_existing_release_bindings_for_update_cursor", return_value=expected["bindings"]),
            patch.object(mesql_v2, "_select_initial_queue_cursor", return_value=[expected["initial_queue"]]) as queue_reader,
        ):
            mesql_v2._validate_work_order_release_invariants_cursor(object(), expected)
        self.assertEqual(queue_reader.call_args.args[2], expected["operations"][0]["work_order_operation_id"])

    def test_invariant_recomputes_and_rejects_digest_mismatch(self) -> None:
        expected = self._invariant_fixture(released=False)
        expected["release"]["operation_set_digest"] = "0" * 64
        with (
            patch.object(mesql_v2, "_get_work_order_route_release_with_cursor", return_value=expected["release"]),
            patch.object(mesql_v2, "_select_work_order_for_release_cursor", return_value={"status": "queued"}),
            patch.object(mesql_v2, "_list_existing_work_order_operations_for_update_cursor", return_value=expected["operations"]),
            patch.object(mesql_v2, "_list_existing_release_bindings_for_update_cursor", return_value=expected["bindings"]),
            patch.object(mesql_v2, "_select_initial_queue_cursor", return_value=[expected["initial_queue"]]),
        ):
            with self.assertRaisesRegex(mesql_v2.MesqlV2Error, "MAPPING_CONFLICT"):
                mesql_v2._validate_work_order_release_invariants_cursor(object(), expected)

    def test_private_primitives_do_not_reference_connection_control(self) -> None:
        for name in (
            "_select_work_order_for_release_cursor",
            "_select_releases_for_update_cursor",
            "_select_exact_process_route_cursor",
            "_select_route_item_cursor",
            "_list_process_route_operations_cursor",
            "_list_existing_work_order_operations_for_update_cursor",
            "_list_existing_release_bindings_for_update_cursor",
            "_list_work_order_release_evidence_cursor",
            "_select_initial_queue_cursor",
            "_lock_station_queue_scope_cursor",
            "_insert_work_order_route_release_cursor",
            "_insert_route_generated_work_order_operation_cursor",
            "_insert_work_order_operation_route_binding_cursor",
            "_insert_initial_station_queue_cursor",
            "_update_work_order_released_state_cursor",
            "_validate_work_order_release_invariants_cursor",
            "_read_work_order_release_snapshot_cursor",
        ):
            source = inspect.getsource(getattr(mesql_v2, name))
            self.assertNotIn("database_connection", source)
            self.assertNotIn("commit", source)
            self.assertNotIn("rollback", source)

    def test_cursor_primitive_propagates_database_error_identity(self) -> None:
        failure = RuntimeError("database failure")

        class RaisingCursor:
            def execute(self, sql, params):
                raise failure

        with self.assertRaises(RuntimeError) as error:
            mesql_v2._select_work_order_for_release_cursor(RaisingCursor(), "WO-1")
        self.assertIs(error.exception, failure)

    def test_cursor_primitive_never_opens_database_connection(self) -> None:
        cursor = _ReleasePrimitiveCursor([("one", None)])
        with patch.object(
            mesql_v2,
            "database_connection",
            side_effect=AssertionError("connection must remain caller-owned"),
        ) as connection_factory:
            self.assertIsNone(
                mesql_v2._select_work_order_for_release_cursor(cursor, "WO-1")
            )
        connection_factory.assert_not_called()

    def test_public_writer_is_phase_5d_c_entrypoint(self) -> None:
        self.assertTrue(callable(mesql_v2.release_work_order_to_route))

    def test_public_read_signatures_remain_exact(self) -> None:
        expected = {
            "get_work_order_route_release": ["config", "work_order_id"],
            "get_work_order_route_release_by_id": ["config", "release_id"],
            "get_exact_process_route": ["config", "route_code", "route_version"],
            "list_process_route_operations": ["config", "process_route_id"],
            "get_work_order_release_snapshot": ["config", "work_order_id"],
        }
        for name, parameters in expected.items():
            self.assertEqual(list(inspect.signature(getattr(mesql_v2, name)).parameters), parameters)

    def test_full_work_order_mapper_supports_tuple_and_dict_rows(self) -> None:
        values = (
            1, "WO-1", "PP", "planned", "ITEM-1", Decimal("2.5"), None,
            None, "mes_web", None, None, {"a": 1}, {"b": 2},
            datetime(2026, 1, 1), datetime(2026, 1, 2),
        )
        names = (
            "work_order_pk", "order_id", "erp_type", "status", "product_code",
            "target_quantity", "started_at", "completed_at", "source_system",
            "source_file", "external_ref", "payload", "metadata", "created_at",
            "updated_at",
        )
        tuple_row = mesql_v2._release_work_order_full_row(values)
        dict_row = mesql_v2._release_work_order_full_row(dict(zip(names, values)))
        self.assertEqual(tuple_row, dict_row)
        self.assertEqual(tuple_row["target_quantity"], 2.5)
        self.assertEqual(tuple_row["created_at"], "2026-01-01T00:00:00")

    def test_full_operation_mapper_supports_tuple_and_dict_rows(self) -> None:
        values = (
            UUID(self.operation_id), "WO-1", None, 10, "OP-10", "First", 10,
            "ST-1", "queued", Decimal("2"), Decimal("0"), Decimal("0"), "EA",
            None, None, {}, {}, datetime(2026, 1, 1), datetime(2026, 1, 2),
        )
        names = (
            "work_order_operation_id", "order_id", "mesql_work_order_operation_id",
            "operation_no", "operation_code", "operation_name", "sequence_no",
            "station_code", "status", "planned_quantity", "good_quantity",
            "scrap_quantity", "uom_code", "started_at", "completed_at", "payload",
            "metadata", "created_at", "updated_at",
        )
        tuple_row = mesql_v2._release_work_order_operation_full_row(values)
        dict_row = mesql_v2._release_work_order_operation_full_row(dict(zip(names, values)))
        self.assertEqual(tuple_row, dict_row)
        self.assertEqual(tuple_row["work_order_operation_id"], self.operation_id)

    def test_combined_release_selector_uses_both_identity_parameters(self) -> None:
        release = (
            1, "R-1", "WO-1", "PR-1", "ROUTE-1", 1, "route_generated",
            "local_planning", "planner", datetime(2026, 1, 1), 1, "a" * 64,
            {}, datetime(2026, 1, 1),
        )
        cursor = _ReleasePrimitiveCursor([("all", [release])])
        rows = mesql_v2._select_releases_for_update_cursor(cursor, "WO-1", "R-1")
        self.assertEqual(rows[0]["release_id"], "R-1")
        self.assertEqual(cursor.executed[0][1], {"work_order_id": "WO-1", "release_id": "R-1"})

    def test_evidence_mapper_returns_all_five_counts(self) -> None:
        cursor = _ReleasePrimitiveCursor([("one", (1, 2, 3, 4, 5))])
        result = mesql_v2._list_work_order_release_evidence_cursor(cursor, "WO-1")
        self.assertEqual(list(result.values()), [1, 2, 3, 4, 5])

    def test_evidence_missing_row_returns_zero_shape(self) -> None:
        cursor = _ReleasePrimitiveCursor([("one", None)])
        result = mesql_v2._list_work_order_release_evidence_cursor(cursor, "WO-1")
        self.assertEqual(sum(result.values()), 0)
        self.assertEqual(len(result), 5)

    def test_initial_queue_selector_returns_empty_list(self) -> None:
        cursor = _ReleasePrimitiveCursor([("all", [])])
        self.assertEqual(
            mesql_v2._select_initial_queue_cursor(cursor, "WO-1", self.operation_id),
            [],
        )

    def test_queue_lock_clamps_mocked_negative_rank_to_zero(self) -> None:
        cursor = _ReleasePrimitiveCursor([
            ("one", (None,)), ("all", []), ("one", (-5,)),
        ])
        result = mesql_v2._lock_station_queue_scope_cursor(cursor, "ST-1")
        self.assertEqual(result["next_queue_rank"], 0)

    def test_queue_lock_reuses_exact_station_parameter(self) -> None:
        cursor = _ReleasePrimitiveCursor([
            ("one", (None,)), ("all", []), ("one", (0,)),
        ])
        mesql_v2._lock_station_queue_scope_cursor(cursor, "ST-9")
        self.assertTrue(all(params == {"station_code": "ST-9"} for _, params in cursor.executed))

    def test_release_insert_maps_returned_row(self) -> None:
        row = (
            1, "R-1", "WO-1", "PR-1", "ROUTE-1", 1, "route_generated",
            "local_planning", "planner", datetime(2026, 1, 1), 1, "a" * 64,
            {}, datetime(2026, 1, 1),
        )
        cursor = _ReleasePrimitiveCursor([("one", row)])
        request = {
            "release_id": "R-1", "order_id": "WO-1", "process_route_id": "PR-1",
            "route_code": "ROUTE-1", "route_version": 1,
            "release_mode": "route_generated", "release_source": "local_planning",
            "released_by": "planner", "route_operation_count": 1,
            "operation_set_digest": "a" * 64, "metadata": {},
        }
        result = mesql_v2._insert_work_order_route_release_cursor(cursor, request)
        self.assertEqual(result["release_pk"], 1)
        self.assertEqual(set(cursor.executed[0][1]), set(request))

    def test_lifecycle_insert_supplies_deterministic_uuid_parameter(self) -> None:
        operation = self._operation_snapshots()[0]
        returned = tuple(operation.get(name) for name in (
            "work_order_operation_id", "order_id", "mesql_work_order_operation_id",
            "operation_no", "operation_code", "operation_name", "sequence_no",
            "station_code", "status", "planned_quantity", "good_quantity",
            "scrap_quantity", "uom_code", "started_at", "completed_at", "payload",
            "metadata",
        )) + (datetime(2026, 1, 1), datetime(2026, 1, 1))
        cursor = _ReleasePrimitiveCursor([("one", returned)])
        mesql_v2._insert_route_generated_work_order_operation_cursor(cursor, operation)
        self.assertEqual(
            cursor.executed[0][1]["work_order_operation_id"],
            operation["work_order_operation_id"],
        )

    def test_binding_insert_uses_exact_snapshot_parameters(self) -> None:
        binding = mesql_v2._build_work_order_release_binding_snapshots(
            release_id=self.release_id, released_by="planner",
            route_operations=self._route_operations(),
            operation_snapshots=self._operation_snapshots(),
        )[0]
        returned = (
            1, binding["binding_id"], binding["work_order_operation_id"],
            binding["route_operation_id"], binding["binding_source"],
            binding["bound_by"], datetime(2026, 1, 1), binding["metadata"],
            datetime(2026, 1, 1),
        )
        cursor = _ReleasePrimitiveCursor([("one", returned)])
        result = mesql_v2._insert_work_order_operation_route_binding_cursor(
            cursor, binding
        )
        self.assertEqual(result["binding_id"], binding["binding_id"])
        self.assertEqual(
            set(cursor.executed[0][1]),
            {"binding_id", "work_order_operation_id", "route_operation_id",
             "binding_source", "bound_by", "metadata"},
        )

    def test_queue_insert_uses_exact_snapshot_parameters(self) -> None:
        queue = mesql_v2._build_initial_queue_snapshot(
            release_id=self.release_id,
            operation_snapshot=self._operation_snapshots()[0], queue_rank=4,
        )
        returned = (
            1, queue["station_code"], queue["order_id"], queue["queue_rank"],
            queue["status"], queue["source"], queue["payload"], queue["metadata"],
            datetime(2026, 1, 1), datetime(2026, 1, 1),
            queue["work_order_operation_id"],
        )
        cursor = _ReleasePrimitiveCursor([("one", returned)])
        result = mesql_v2._insert_initial_station_queue_cursor(cursor, queue)
        self.assertEqual(result["queue_rank"], 4)
        self.assertEqual(set(cursor.executed[0][1]), set(queue))

    def test_work_order_update_uses_only_identity_parameter(self) -> None:
        returned = (
            1, "WO-1", "PP", "queued", "ITEM-1", 5, None, None,
            "mes_web", None, None, {}, {}, datetime(2026, 1, 1),
            datetime(2026, 1, 2),
        )
        cursor = _ReleasePrimitiveCursor([("one", returned)])
        result = mesql_v2._update_work_order_released_state_cursor(cursor, "WO-1")
        self.assertEqual(result["status"], "queued")
        self.assertEqual(cursor.executed[0][1], {"work_order_id": "WO-1"})

    def test_release_comparator_rejects_metadata_mismatch(self) -> None:
        expected = {name: name for name in (
            "release_id", "order_id", "process_route_id", "route_code",
            "route_version", "release_mode", "release_source", "released_by",
            "route_operation_count", "operation_set_digest", "metadata",
        )}
        persisted = {**expected, "metadata": {"different": True}}
        self.assertFalse(mesql_v2._compare_immutable_release_request(persisted, expected))

    def test_static_operation_comparison_rejects_extra_operation(self) -> None:
        expected = self._operation_snapshots()
        self.assertFalse(
            mesql_v2._compare_static_operation_snapshots(expected + [expected[0]], expected)
        )

    def test_complete_binding_comparison_accepts_input_order_difference(self) -> None:
        expected = [
            {"binding_id": "B1", "work_order_operation_id": "O1", "route_operation_id": "R1", "binding_source": "work_order_release", "bound_by": "p", "metadata": {}},
            {"binding_id": "B2", "work_order_operation_id": "O2", "route_operation_id": "R2", "binding_source": "work_order_release", "bound_by": "p", "metadata": {}},
        ]
        self.assertTrue(mesql_v2._compare_complete_binding_set(list(reversed(expected)), expected))

    def test_operation_builder_does_not_mutate_route_operations(self) -> None:
        operations = self._route_operations()
        original = deepcopy(operations)
        mesql_v2._build_route_generated_operation_snapshots(
            release_id=self.release_id, work_order_id="WO-1",
            process_route=self._route(), route_item=self._item(),
            route_operations=operations, target_quantity=1,
        )
        self.assertEqual(operations, original)

    def test_binding_builder_does_not_mutate_inputs(self) -> None:
        routes = self._route_operations()
        operations = self._operation_snapshots()
        expected_routes = deepcopy(routes)
        expected_operations = deepcopy(operations)
        mesql_v2._build_work_order_release_binding_snapshots(
            release_id=self.release_id, released_by="planner",
            route_operations=routes, operation_snapshots=operations,
        )
        self.assertEqual(routes, expected_routes)
        self.assertEqual(operations, expected_operations)

    def test_existing_public_binding_insert_contract_remains_upsert_free_update(self) -> None:
        sql = mesql_v2.INSERT_WORK_ORDER_OPERATION_ROUTE_BINDING_SQL.lower()
        self.assertIn("on conflict do nothing", sql)
        self.assertNotIn("do update", sql)


class _WriterCursor:
    def __init__(self) -> None:
        self.executed: list[tuple[str, dict]] = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.closed = True
        return False

    def execute(self, sql: str, params: dict | None = None) -> None:
        if self.closed:
            raise AssertionError("closed cursor reused")
        self.executed.append((sql, params or {}))


class _WriterTransaction:
    def __init__(self, connection) -> None:
        self.connection = connection
        self.backup = None

    def __enter__(self):
        self.connection.transaction_enters += 1
        self.backup = deepcopy(self.connection.state)
        return self

    def __exit__(self, exc_type, exc, traceback):
        if exc is not None or self.connection.fail_on_exit:
            self.connection.state.clear()
            self.connection.state.update(self.backup)
            self.connection.rollbacks += 1
            if exc is None and self.connection.fail_on_exit:
                raise RuntimeError("before transaction exit")
            return False
        self.connection.commits += 1
        return False


class _WriterConnection:
    def __init__(self, state=None, *, fail_on_exit=False) -> None:
        self.state = state if state is not None else {}
        self.fail_on_exit = fail_on_exit
        self.cursor_instance = _WriterCursor()
        self.cursor_calls = 0
        self.transaction_calls = 0
        self.transaction_enters = 0
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def transaction(self):
        self.transaction_calls += 1
        return _WriterTransaction(self)

    def cursor(self):
        self.cursor_calls += 1
        return self.cursor_instance


class _WriterDatabaseFactory:
    def __init__(self, connections) -> None:
        self.connections = list(connections)
        self.calls = 0
        self.events: list[str] = []

    def __call__(self, config):
        index = self.calls
        self.calls += 1
        connection = self.connections[index]

        @contextmanager
        def context():
            self.events.append(f"enter:{index}")
            try:
                yield connection
            finally:
                connection.closed = True
                self.events.append(f"close:{index}")

        return context()


class _FakePgError(RuntimeError):
    def __init__(self, sqlstate, constraint_name=None) -> None:
        super().__init__(sqlstate)
        self.sqlstate = sqlstate

        class Diagnostic:
            pass

        self.diag = Diagnostic()
        self.diag.sqlstate = sqlstate
        self.diag.constraint_name = constraint_name


class WorkOrderReleaseWriterTests(unittest.TestCase):
    def _base_kwargs(self):
        return {
            "release_id": "RELEASE-200",
            "work_order_id": "WO-200",
            "route_code": "ROUTE-2",
            "route_version": 2,
            "release_source": "local_planning",
            "released_by": "planner",
            "mode": "route_generated",
            "operation_bindings": None,
            "metadata": {"request": "phase-5d-c"},
        }

    def _request(self):
        return mesql_v2._normalize_work_order_release_request(
            **self._base_kwargs()
        )

    def _route_operations(self):
        return [
            {
                "route_operation_id": "ROP-10", "route_code": "ROUTE-2",
                "route_version": 2, "sequence_no": 10,
                "operation_code": "OP-10", "operation_name": "First",
                "station_code": "ST-1", "active": True,
            },
            {
                "route_operation_id": "ROP-20", "route_code": "ROUTE-2",
                "route_version": 2, "sequence_no": 20,
                "operation_code": "OP-20", "operation_name": "Second",
                "station_code": "ST-2", "active": True,
            },
        ]

    def _context(self, *, existing=False):
        request = self._request()
        process_route = {
            "route_id": "ROUTE-ID-2", "route_code": "ROUTE-2", "version": 2,
            "route_name": "Route", "item_code": "ITEM-1", "active": True,
            "metadata": {},
        }
        route_item = {
            "item_code": "ITEM-1", "item_name": "Item", "item_type": "product",
            "unit": "EA", "active": True, "metadata": {},
        }
        route_operations = self._route_operations()
        operations = mesql_v2._build_route_generated_operation_snapshots(
            release_id=request["release_id"], work_order_id=request["work_order_id"],
            process_route=process_route, route_item=route_item,
            route_operations=route_operations, target_quantity=5,
        )
        bindings = mesql_v2._build_work_order_release_binding_snapshots(
            release_id=request["release_id"], released_by=request["released_by"],
            route_operations=route_operations, operation_snapshots=operations,
        )
        binding_by_operation = {
            binding["work_order_operation_id"]: binding for binding in bindings
        }
        digest = mesql_v2._compute_work_order_release_operation_set_digest(
            process_route_id=process_route["route_id"],
            route_code=process_route["route_code"], route_version=2,
            release_mode=request["mode"],
            pairs=[
                {
                    "sequence_no": operation["sequence_no"],
                    "route_operation_id": binding_by_operation[
                        operation["work_order_operation_id"]
                    ]["route_operation_id"],
                    "work_order_operation_id": operation[
                        "work_order_operation_id"
                    ],
                }
                for operation in operations
            ],
        )
        release = {
            "release_id": request["release_id"], "order_id": request["work_order_id"],
            "process_route_id": process_route["route_id"],
            "route_code": process_route["route_code"], "route_version": 2,
            "release_mode": request["mode"],
            "release_source": request["release_source"],
            "released_by": request["released_by"],
            "route_operation_count": 2, "operation_set_digest": digest,
            "metadata": request["metadata"],
        }
        queue = mesql_v2._build_initial_queue_snapshot(
            release_id=request["release_id"], operation_snapshot=operations[0],
            queue_rank=3,
        )
        return {
            "work_order": {
                "order_id": request["work_order_id"], "status": "planned",
                "product_code": "ITEM-1", "target_quantity": 5,
                "started_at": None, "completed_at": None,
            },
            "existing_release": deepcopy(release) if existing else None,
            "process_route": process_route, "route_item": route_item,
            "route_operations": route_operations,
            "existing_operations": deepcopy(operations) if existing else [],
            "existing_bindings": deepcopy(bindings) if existing else [],
            "evidence": {}, "existing_queue": [deepcopy(queue)] if existing else [],
            "release_snapshot": release, "operation_snapshots": operations,
            "binding_snapshots": bindings, "initial_queue_snapshot": queue,
        }

    def _response(self, context, released):
        return {
            "released": released,
            "release": deepcopy(context["release_snapshot"]),
            "work_order": deepcopy(context["work_order"]),
            "operations": deepcopy(context["operation_snapshots"]),
            "bindings": deepcopy(context["binding_snapshots"]),
            "initial_queue": deepcopy(context["initial_queue_snapshot"]),
        }

    def test_public_writer_signature_is_exact(self) -> None:
        self.assertEqual(
            list(inspect.signature(mesql_v2.release_work_order_to_route).parameters),
            [
                "config", "release_id", "work_order_id", "route_code",
                "route_version", "release_source", "released_by", "mode",
                "operation_bindings", "metadata",
            ],
        )

    def test_metadata_is_json_safe_and_not_merged(self) -> None:
        captured = {}

        def run(config, request):
            captured.update(request)
            return {"released": True}

        kwargs = self._base_kwargs()
        kwargs["metadata"] = {
            "quantity": Decimal("2.5"),
            "at": datetime(2026, 7, 15),
        }
        with patch.object(mesql_v2, "_run_work_order_release_transaction", run):
            mesql_v2.release_work_order_to_route(object(), **kwargs)
        self.assertEqual(
            captured["metadata"],
            {"quantity": 2.5, "at": "2026-07-15T00:00:00"},
        )
        self.assertEqual(set(captured["metadata"]), {"quantity", "at"})

    def test_omitted_metadata_normalizes_to_empty_object(self) -> None:
        kwargs = self._base_kwargs()
        kwargs["metadata"] = None
        with patch.object(
            mesql_v2, "_run_work_order_release_transaction",
            side_effect=lambda config, request: request,
        ):
            request = mesql_v2.release_work_order_to_route(object(), **kwargs)
        self.assertEqual(request["metadata"], {})

    def test_empty_generated_operation_mapping_is_allowed(self) -> None:
        kwargs = self._base_kwargs()
        kwargs["operation_bindings"] = []
        with patch.object(
            mesql_v2, "_run_work_order_release_transaction",
            side_effect=lambda config, request: request,
        ):
            request = mesql_v2.release_work_order_to_route(object(), **kwargs)
        self.assertEqual(request["mode"], "route_generated")

    def test_recursive_metadata_is_rejected_before_database(self) -> None:
        recursive = {}
        recursive["self"] = recursive
        kwargs = self._base_kwargs()
        kwargs["metadata"] = recursive
        with patch.object(
            mesql_v2, "database_connection",
            side_effect=AssertionError("database must not open"),
        ) as connection_factory:
            with self.assertRaisesRegex(
                mesql_v2.MesqlV2Error, "RELEASE_METADATA_INVALID"
            ):
                mesql_v2.release_work_order_to_route(object(), **kwargs)
        connection_factory.assert_not_called()

    def test_phase_5d_b_primitive_signatures_remain_stable(self) -> None:
        expected = {
            "_select_work_order_for_release_cursor": ["cursor", "work_order_id"],
            "_select_releases_for_update_cursor": [
                "cursor", "work_order_id", "release_id"
            ],
            "_select_exact_process_route_cursor": [
                "cursor", "route_code", "route_version"
            ],
            "_select_route_item_cursor": ["cursor", "item_code"],
            "_list_process_route_operations_cursor": [
                "cursor", "process_route_id"
            ],
            "_list_existing_work_order_operations_for_update_cursor": [
                "cursor", "work_order_id"
            ],
            "_list_existing_release_bindings_for_update_cursor": [
                "cursor", "work_order_id"
            ],
            "_list_work_order_release_evidence_cursor": [
                "cursor", "work_order_id"
            ],
            "_select_initial_queue_cursor": [
                "cursor", "work_order_id", "work_order_operation_id"
            ],
            "_lock_station_queue_scope_cursor": ["cursor", "station_code"],
            "_insert_work_order_route_release_cursor": [
                "cursor", "release_snapshot"
            ],
            "_insert_route_generated_work_order_operation_cursor": [
                "cursor", "operation_snapshot"
            ],
            "_insert_work_order_operation_route_binding_cursor": [
                "cursor", "binding_snapshot"
            ],
            "_insert_initial_station_queue_cursor": [
                "cursor", "queue_snapshot"
            ],
            "_update_work_order_released_state_cursor": [
                "cursor", "work_order_id"
            ],
        }
        for name, parameters in expected.items():
            self.assertEqual(
                list(inspect.signature(getattr(mesql_v2, name)).parameters),
                parameters,
            )

    def test_first_release_owns_one_connection_transaction_and_cursor(self) -> None:
        connection = _WriterConnection({})
        factory = _WriterDatabaseFactory([connection])
        response = {"released": True}
        with (
            patch.object(mesql_v2, "database_connection", factory),
            patch.object(
                mesql_v2, "_release_work_order_to_route_cursor",
                return_value=response,
            ),
        ):
            result = mesql_v2.release_work_order_to_route(
                object(), **self._base_kwargs()
            )
        self.assertIs(result, response)
        self.assertEqual(factory.calls, 1)
        self.assertEqual(connection.transaction_calls, 1)
        self.assertEqual(connection.cursor_calls, 1)
        self.assertEqual(connection.commits, 1)
        self.assertEqual(connection.rollbacks, 0)
        self.assertTrue(connection.closed)
        self.assertEqual(
            connection.cursor_instance.executed[0][0],
            mesql_v2.SET_WORK_ORDER_RELEASE_TRANSACTION_ISOLATION_SQL,
        )

    def test_first_release_insert_and_validation_order(self) -> None:
        context = self._context(existing=False)
        events = []
        response = self._response(context, True)
        with ExitStack() as stack:
            stack.enter_context(patch.object(
                mesql_v2, "_prepare_work_order_release_context_cursor",
                side_effect=lambda cursor, request: events.append("prepare") or context,
            ))
            stack.enter_context(patch.object(
                mesql_v2, "_lock_station_queue_scope_cursor",
                side_effect=lambda cursor, station: events.append("queue_lock") or {
                    "station_code": station, "next_queue_rank": 3, "rows": []
                },
            ))
            for name, label in (
                ("_insert_work_order_route_release_cursor", "release"),
                ("_insert_route_generated_work_order_operation_cursor", "operation"),
                ("_insert_work_order_operation_route_binding_cursor", "binding"),
                ("_insert_initial_station_queue_cursor", "queue"),
                ("_update_work_order_released_state_cursor", "work_order"),
            ):
                stack.enter_context(patch.object(
                    mesql_v2, name,
                    side_effect=lambda *args, _label=label, **kwargs: events.append(_label) or {},
                ))
            stack.enter_context(patch.object(
                mesql_v2, "_validate_work_order_release_invariants_cursor",
                side_effect=lambda *args: events.append("invariant") or {},
            ))
            stack.enter_context(patch.object(
                mesql_v2, "_work_order_release_response_cursor",
                side_effect=lambda *args, **kwargs: events.append("snapshot") or response,
            ))
            result = mesql_v2._release_work_order_to_route_cursor(
                object(), self._request()
            )
        self.assertIs(result, response)
        self.assertEqual(events, [
            "prepare", "queue_lock", "release", "operation", "operation",
            "binding", "binding", "queue", "work_order", "invariant", "snapshot",
        ])

    def test_prepare_context_uses_normative_read_and_lock_order(self) -> None:
        source = self._context(existing=False)
        events = []

        def value(label, result):
            return lambda *args, **kwargs: events.append(label) or result

        with (
            patch.object(mesql_v2, "_select_work_order_for_release_cursor", side_effect=value("work_order", source["work_order"])),
            patch.object(mesql_v2, "_select_releases_for_update_cursor", side_effect=value("releases", [])),
            patch.object(mesql_v2, "_select_exact_process_route_cursor", side_effect=value("route", source["process_route"])),
            patch.object(mesql_v2, "_select_route_item_cursor", side_effect=value("item", source["route_item"])),
            patch.object(mesql_v2, "_list_process_route_operations_cursor", side_effect=value("route_operations", source["route_operations"])),
            patch.object(mesql_v2, "_validate_route_generated_config", side_effect=value("config", None)),
            patch.object(mesql_v2, "_list_existing_work_order_operations_for_update_cursor", side_effect=value("operations", [])),
            patch.object(mesql_v2, "_list_existing_release_bindings_for_update_cursor", side_effect=value("bindings", [])),
            patch.object(mesql_v2, "_list_work_order_release_evidence_cursor", side_effect=value("evidence", {})),
            patch.object(mesql_v2, "_list_existing_work_order_queue_for_update_cursor", side_effect=value("queue", [])),
        ):
            result = mesql_v2._prepare_work_order_release_context_cursor(
                object(), self._request()
            )
        self.assertIsNone(result["existing_release"])
        self.assertEqual(events, [
            "work_order", "releases", "route", "item", "route_operations",
            "config", "operations", "bindings", "evidence", "queue",
        ])

    def test_replay_performs_zero_writes_and_zero_advisory_locks(self) -> None:
        context = self._context(existing=True)
        response = self._response(context, False)
        forbidden = (
            "_lock_station_queue_scope_cursor",
            "_insert_work_order_route_release_cursor",
            "_insert_route_generated_work_order_operation_cursor",
            "_insert_work_order_operation_route_binding_cursor",
            "_insert_initial_station_queue_cursor",
            "_update_work_order_released_state_cursor",
        )
        with ExitStack() as stack:
            stack.enter_context(patch.object(
                mesql_v2, "_prepare_work_order_release_context_cursor",
                return_value=context,
            ))
            for name in forbidden:
                stack.enter_context(patch.object(
                    mesql_v2, name, side_effect=AssertionError(name)
                ))
            stack.enter_context(patch.object(
                mesql_v2, "_validate_work_order_release_invariants_cursor",
                return_value={},
            ))
            stack.enter_context(patch.object(
                mesql_v2, "_work_order_release_response_cursor",
                return_value=response,
            ))
            result = mesql_v2._release_work_order_to_route_cursor(
                object(), self._request()
            )
        self.assertFalse(result["released"])

    def test_replay_returns_authoritative_reader_response(self) -> None:
        context = self._context(existing=True)
        authoritative = self._response(context, False)
        authoritative["work_order"]["status"] = "completed"
        authoritative["operations"][0]["good_quantity"] = 5
        with (
            patch.object(
                mesql_v2, "_prepare_work_order_release_context_cursor",
                return_value=context,
            ),
            patch.object(
                mesql_v2, "_validate_work_order_release_invariants_cursor",
                return_value={},
            ),
            patch.object(
                mesql_v2, "_work_order_release_response_cursor",
                return_value=authoritative,
            ) as reader,
        ):
            result = mesql_v2._release_work_order_to_route_cursor(
                object(), self._request()
            )
        self.assertIs(result, authoritative)
        reader.assert_called_once()

    def test_replay_config_does_not_reapply_active_eligibility(self) -> None:
        context = self._context(existing=True)
        context["process_route"]["active"] = False
        context["route_item"]["active"] = False
        for operation in context["route_operations"]:
            operation["active"] = False
        mesql_v2._validate_route_generated_replay_config(
            context["process_route"],
            context["route_item"],
            context["route_operations"],
        )
        snapshots = mesql_v2._assemble_route_generated_operation_snapshots(
            release_id=self._request()["release_id"],
            work_order_id=self._request()["work_order_id"],
            process_route=context["process_route"],
            route_item=context["route_item"],
            route_operations=context["route_operations"],
            target_quantity=5,
        )
        self.assertTrue(
            mesql_v2._compare_static_operation_snapshots(
                snapshots, context["existing_operations"]
            )
        )

    def test_order_scoped_queue_lock_sql_is_explicit(self) -> None:
        sql = mesql_v2.SELECT_WORK_ORDER_QUEUE_FOR_UPDATE_CURSOR_SQL.lower()
        self.assertIn("where order_id = %(work_order_id)s", sql)
        self.assertIn("order by station_queue_pk asc", sql)
        self.assertIn("for update", sql)
        self.assertNotIn("select *", sql)

    def test_prepare_missing_work_order_is_404(self) -> None:
        with (
            patch.object(
                mesql_v2, "_select_work_order_for_release_cursor",
                return_value=None,
            ),
            patch.object(
                mesql_v2, "_select_releases_for_update_cursor",
                return_value=[],
            ),
        ):
            with self.assertRaises(mesql_v2.MesqlV2Error) as error:
                mesql_v2._prepare_work_order_release_context_cursor(
                    object(), self._request()
                )
        self.assertEqual(error.exception.detail, "WORK_ORDER_NOT_FOUND")
        self.assertEqual(error.exception.status_code, 404)

    def test_prepare_missing_exact_route_is_404(self) -> None:
        context = self._context(existing=False)
        with (
            patch.object(
                mesql_v2, "_select_work_order_for_release_cursor",
                return_value=context["work_order"],
            ),
            patch.object(
                mesql_v2, "_select_releases_for_update_cursor",
                return_value=[],
            ),
            patch.object(
                mesql_v2, "_select_exact_process_route_cursor",
                return_value=None,
            ),
        ):
            with self.assertRaises(mesql_v2.MesqlV2Error) as error:
                mesql_v2._prepare_work_order_release_context_cursor(
                    object(), self._request()
                )
        self.assertEqual(error.exception.detail, "PROCESS_ROUTE_NOT_FOUND")
        self.assertEqual(error.exception.status_code, 404)

    def test_prepare_missing_route_operations_is_404(self) -> None:
        context = self._context(existing=False)
        with (
            patch.object(
                mesql_v2, "_select_work_order_for_release_cursor",
                return_value=context["work_order"],
            ),
            patch.object(
                mesql_v2, "_select_releases_for_update_cursor",
                return_value=[],
            ),
            patch.object(
                mesql_v2, "_select_exact_process_route_cursor",
                return_value=context["process_route"],
            ),
            patch.object(
                mesql_v2, "_select_route_item_cursor",
                return_value=context["route_item"],
            ),
            patch.object(
                mesql_v2, "_list_process_route_operations_cursor",
                return_value=[],
            ),
        ):
            with self.assertRaises(mesql_v2.MesqlV2Error) as error:
                mesql_v2._prepare_work_order_release_context_cursor(
                    object(), self._request()
                )
        self.assertEqual(error.exception.detail, "ROUTE_OPERATION_NOT_FOUND")
        self.assertEqual(error.exception.status_code, 404)

    def test_database_disabled_is_503(self) -> None:
        with patch.object(mesql_v2, "database_connection", return_value=nullcontext(None)):
            with self.assertRaises(mesql_v2.MesqlV2Error) as error:
                mesql_v2.release_work_order_to_route(
                    object(), **self._base_kwargs()
                )
        self.assertEqual(error.exception.detail, "DATABASE_DISABLED")
        self.assertEqual(error.exception.status_code, 503)

    def _assert_unique_recovery_replay(self):
        context = self._context(existing=True)
        connections = [_WriterConnection({}), _WriterConnection({})]
        factory = _WriterDatabaseFactory(connections)
        unique_error = _FakePgError(
            "23505", "uq_mes_work_order_route_releases_order_id"
        )
        response = self._response(context, False)
        with (
            patch.object(mesql_v2, "database_connection", factory),
            patch.object(
                mesql_v2, "_release_work_order_to_route_cursor",
                side_effect=unique_error,
            ),
            patch.object(
                mesql_v2, "_prepare_work_order_release_context_cursor",
                return_value=context,
            ),
            patch.object(
                mesql_v2, "_validate_work_order_release_invariants_cursor",
                return_value={},
            ),
            patch.object(
                mesql_v2, "_work_order_release_response_cursor",
                return_value=response,
            ),
        ):
            result = mesql_v2.release_work_order_to_route(
                object(), **self._base_kwargs()
            )
        return result, factory, connections

    def test_23505_exact_readback_returns_replay(self) -> None:
        result, factory, connections = self._assert_unique_recovery_replay()
        self.assertFalse(result["released"])
        self.assertEqual(factory.calls, 2)
        self.assertEqual(connections[0].rollbacks, 1)
        self.assertEqual(connections[1].commits, 1)

    def test_23505_first_context_closes_before_second_opens(self) -> None:
        result, factory, connections = self._assert_unique_recovery_replay()
        self.assertEqual(factory.events, ["enter:0", "close:0", "enter:1", "close:1"])
        self.assertTrue(connections[0].cursor_instance.closed)
        self.assertIsNot(
            connections[0].cursor_instance, connections[1].cursor_instance
        )

    def test_same_request_concurrency_yields_true_then_false(self) -> None:
        context = self._context(existing=True)
        connections = [
            _WriterConnection({}), _WriterConnection({}), _WriterConnection({})
        ]
        factory = _WriterDatabaseFactory(connections)
        first_response = self._response(context, True)
        replay_response = self._response(context, False)
        unique_error = _FakePgError(
            "23505", "uq_mes_work_order_route_releases_order_id"
        )
        with (
            patch.object(mesql_v2, "database_connection", factory),
            patch.object(
                mesql_v2, "_release_work_order_to_route_cursor",
                side_effect=[first_response, unique_error],
            ),
            patch.object(
                mesql_v2, "_prepare_work_order_release_context_cursor",
                return_value=context,
            ),
            patch.object(
                mesql_v2, "_validate_work_order_release_invariants_cursor",
                return_value={},
            ),
            patch.object(
                mesql_v2, "_work_order_release_response_cursor",
                return_value=replay_response,
            ),
        ):
            first = mesql_v2.release_work_order_to_route(
                object(), **self._base_kwargs()
            )
            second = mesql_v2.release_work_order_to_route(
                object(), **self._base_kwargs()
            )
        self.assertEqual([first["released"], second["released"]], [True, False])
        self.assertEqual(connections[0].commits, 1)
        self.assertEqual(connections[1].rollbacks, 1)
        self.assertEqual(connections[2].commits, 1)

    def test_cross_order_release_id_concurrency_yields_true_then_conflict(self) -> None:
        connections = [
            _WriterConnection({}), _WriterConnection({}), _WriterConnection({})
        ]
        factory = _WriterDatabaseFactory(connections)
        first_response = {"released": True}
        unique_error = _FakePgError(
            "23505", "uq_mes_work_order_route_releases_release_id"
        )
        conflict = mesql_v2.MesqlV2Error(
            "WORK_ORDER_ROUTE_RELEASE_ID_CONFLICT", status_code=409
        )
        second_kwargs = self._base_kwargs()
        second_kwargs["work_order_id"] = "WO-OTHER"
        with (
            patch.object(mesql_v2, "database_connection", factory),
            patch.object(
                mesql_v2, "_release_work_order_to_route_cursor",
                side_effect=[first_response, unique_error],
            ),
            patch.object(
                mesql_v2, "_prepare_work_order_release_context_cursor",
                side_effect=conflict,
            ),
        ):
            first = mesql_v2.release_work_order_to_route(
                object(), **self._base_kwargs()
            )
            with self.assertRaises(mesql_v2.MesqlV2Error) as error:
                mesql_v2.release_work_order_to_route(object(), **second_kwargs)
        self.assertTrue(first["released"])
        self.assertIs(error.exception, conflict)
        self.assertEqual(connections[0].commits, 1)
        self.assertEqual(connections[1].rollbacks, 1)

    def test_23505_cross_order_conflict_uses_second_context(self) -> None:
        connections = [_WriterConnection({}), _WriterConnection({})]
        factory = _WriterDatabaseFactory(connections)
        unique_error = _FakePgError("23505")
        conflict = mesql_v2.MesqlV2Error(
            "WORK_ORDER_ROUTE_RELEASE_ID_CONFLICT", status_code=409
        )
        with (
            patch.object(mesql_v2, "database_connection", factory),
            patch.object(
                mesql_v2, "_release_work_order_to_route_cursor",
                side_effect=unique_error,
            ),
            patch.object(
                mesql_v2, "_prepare_work_order_release_context_cursor",
                side_effect=conflict,
            ),
        ):
            with self.assertRaises(mesql_v2.MesqlV2Error) as error:
                mesql_v2.release_work_order_to_route(
                    object(), **self._base_kwargs()
                )
        self.assertIs(error.exception, conflict)
        self.assertEqual(factory.calls, 2)
        self.assertEqual(factory.events[:3], ["enter:0", "close:0", "enter:1"])

    def test_unknown_23505_propagates_original_error(self) -> None:
        connections = [_WriterConnection({}), _WriterConnection({})]
        factory = _WriterDatabaseFactory(connections)
        unique_error = _FakePgError("23505", "unrelated_unique")
        context = self._context(existing=False)
        with (
            patch.object(mesql_v2, "database_connection", factory),
            patch.object(
                mesql_v2, "_release_work_order_to_route_cursor",
                side_effect=unique_error,
            ),
            patch.object(
                mesql_v2, "_prepare_work_order_release_context_cursor",
                return_value=context,
            ),
        ):
            with self.assertRaises(_FakePgError) as error:
                mesql_v2.release_work_order_to_route(
                    object(), **self._base_kwargs()
                )
        self.assertIs(error.exception, unique_error)
        self.assertEqual(factory.calls, 2)

    def test_queue_rank_23505_maps_to_queue_conflict_without_retry(self) -> None:
        connections = [_WriterConnection({}), _WriterConnection({})]
        factory = _WriterDatabaseFactory(connections)
        unique_error = _FakePgError(
            "23505", "uq_mes_station_queue_station_active_rank"
        )
        context = self._context(existing=False)
        with (
            patch.object(mesql_v2, "database_connection", factory),
            patch.object(
                mesql_v2, "_release_work_order_to_route_cursor",
                side_effect=unique_error,
            ),
            patch.object(
                mesql_v2, "_prepare_work_order_release_context_cursor",
                return_value=context,
            ),
        ):
            with self.assertRaisesRegex(mesql_v2.MesqlV2Error, "QUEUE_CONFLICT"):
                mesql_v2.release_work_order_to_route(
                    object(), **self._base_kwargs()
                )
        self.assertEqual(factory.calls, 2)
        self.assertEqual(connections[0].rollbacks, 1)
        self.assertEqual(connections[1].rollbacks, 1)

    def _run_conflict_case(self, scenario, expected_detail):
        request = self._request()
        context = self._context(existing=True)
        if scenario == "release_id_other_order":
            release = deepcopy(context["existing_release"])
            release["order_id"] = "WO-OTHER"
            callable_ = lambda: mesql_v2._classify_release_identity_conflicts(
                [release], request
            )
        elif scenario == "already_released":
            release = deepcopy(context["existing_release"])
            release["release_id"] = "RELEASE-OTHER"
            callable_ = lambda: mesql_v2._classify_release_identity_conflicts(
                [release], request
            )
        elif scenario in {"route_code", "route_version", "mode", "source", "actor", "metadata"}:
            release = deepcopy(context["existing_release"])
            field, value = {
                "route_code": ("route_code", "ROUTE-OTHER"),
                "route_version": ("route_version", 3),
                "mode": ("release_mode", "explicit_existing_operation_mapping"),
                "source": ("release_source", "mesql"),
                "actor": ("released_by", "other"),
                "metadata": ("metadata", {"different": True}),
            }[scenario]
            release[field] = value
            callable_ = lambda: mesql_v2._classify_release_identity_conflicts(
                [release], request
            )
        else:
            if scenario == "operation_count":
                context["existing_release"]["route_operation_count"] = 1
            elif scenario == "missing_operation":
                context["existing_operations"] = context["existing_operations"][:1]
            elif scenario == "static_operation":
                context["existing_operations"][0]["station_code"] = "OTHER"
            elif scenario == "partial_binding":
                context["existing_bindings"] = context["existing_bindings"][:1]
            elif scenario == "mapping":
                context["existing_bindings"][0]["route_operation_id"] = "OTHER"
            elif scenario == "digest":
                context["existing_release"]["operation_set_digest"] = "0" * 64
            elif scenario == "queue_missing":
                context["existing_queue"] = []
            elif scenario == "queue_extra":
                context["existing_queue"].append(
                    deepcopy(context["existing_queue"][0])
                )
            elif scenario == "queue_identity":
                context["existing_queue"][0]["source"] = "other"
            callable_ = lambda: mesql_v2._validate_existing_work_order_release_replay(
                context
            )
        with self.assertRaises(mesql_v2.MesqlV2Error) as error:
            callable_()
        self.assertEqual(error.exception.detail, expected_detail)
        self.assertEqual(error.exception.status_code, 409)

    def _run_mutable_replay_case(self, scenario):
        context = self._context(existing=True)
        if scenario == "work_order_status":
            context["work_order"]["status"] = "completed"
        elif scenario == "operation_status":
            context["existing_operations"][0]["status"] = "completed"
        elif scenario == "actual_quantities":
            context["existing_operations"][0].update({
                "good_quantity": 4, "scrap_quantity": 1
            })
        elif scenario == "operation_timestamps":
            context["existing_operations"][0].update({
                "started_at": "start", "completed_at": "end", "updated_at": "later"
            })
        elif scenario == "queue_status":
            context["existing_queue"][0]["status"] = "active"
        elif scenario == "queue_rank":
            context["existing_queue"][0]["queue_rank"] = 99
        elif scenario == "queue_timestamp":
            context["existing_queue"][0]["updated_at"] = "later"
        mesql_v2._validate_existing_work_order_release_replay(context)

    def _run_nonunique_error_case(self, sqlstate):
        connection = _WriterConnection({})
        factory = _WriterDatabaseFactory([connection])
        database_error = _FakePgError(sqlstate)
        with (
            patch.object(mesql_v2, "database_connection", factory),
            patch.object(
                mesql_v2, "_release_work_order_to_route_cursor",
                side_effect=database_error,
            ),
        ):
            with self.assertRaises(_FakePgError) as error:
                mesql_v2.release_work_order_to_route(
                    object(), **self._base_kwargs()
                )
        self.assertIs(error.exception, database_error)
        self.assertEqual(factory.calls, 1)
        self.assertEqual(connection.rollbacks, 1)

    def _run_failure_case(self, failure_point):
        context = self._context(existing=False)
        state = {
            "release": 0, "operations": 0, "bindings": 0,
            "queue": 0, "status": "planned",
        }
        failing_connection = _WriterConnection(
            state, fail_on_exit=failure_point == "before_transaction_exit"
        )
        retry_connection = _WriterConnection(state)
        factory = _WriterDatabaseFactory([failing_connection, retry_connection])
        attempt = {"value": 1}
        counters = {"operation": 0, "binding": 0}
        failure = RuntimeError(failure_point)

        def maybe_fail(point):
            if attempt["value"] == 1 and failure_point == point:
                raise failure

        def insert_release(cursor, snapshot):
            state["release"] += 1
            maybe_fail("after_release_insert")
            return {}

        def insert_operation(cursor, snapshot):
            state["operations"] += 1
            counters["operation"] += 1
            if counters["operation"] == 1:
                maybe_fail("after_first_lifecycle_insert")
            if counters["operation"] == 2:
                maybe_fail("after_all_lifecycle_inserts")
            return {}

        def insert_binding(cursor, snapshot):
            state["bindings"] += 1
            counters["binding"] += 1
            if counters["binding"] == 1:
                maybe_fail("after_first_binding")
            if counters["binding"] == 2:
                maybe_fail("after_all_bindings")
            return {}

        def insert_queue(cursor, snapshot):
            state["queue"] += 1
            maybe_fail("after_queue_insert")
            return {}

        def update_work_order(cursor, work_order_id):
            state["status"] = "queued"
            maybe_fail("after_work_order_update")
            return {}

        def invariant(cursor, expected):
            maybe_fail("before_invariant_validation")
            return {}

        def response(cursor, work_order_id, released):
            maybe_fail("before_snapshot_read")
            return self._response(context, released)

        with ExitStack() as stack:
            stack.enter_context(patch.object(mesql_v2, "database_connection", factory))
            if failure_point in {"after_work_order_lock", "after_route_validation"}:
                stack.enter_context(patch.object(
                    mesql_v2, "_select_work_order_for_release_cursor",
                    return_value=context["work_order"],
                ))

                def releases_after_work_order_lock(*args):
                    maybe_fail("after_work_order_lock")
                    return []

                stack.enter_context(patch.object(
                    mesql_v2, "_select_releases_for_update_cursor",
                    side_effect=releases_after_work_order_lock,
                ))
                stack.enter_context(patch.object(
                    mesql_v2, "_select_exact_process_route_cursor",
                    return_value=context["process_route"],
                ))
                stack.enter_context(patch.object(
                    mesql_v2, "_select_route_item_cursor",
                    return_value=context["route_item"],
                ))
                stack.enter_context(patch.object(
                    mesql_v2, "_list_process_route_operations_cursor",
                    return_value=context["route_operations"],
                ))

                def operations_after_route_validation(*args):
                    maybe_fail("after_route_validation")
                    return []

                stack.enter_context(patch.object(
                    mesql_v2,
                    "_list_existing_work_order_operations_for_update_cursor",
                    side_effect=operations_after_route_validation,
                ))
                stack.enter_context(patch.object(
                    mesql_v2,
                    "_list_existing_release_bindings_for_update_cursor",
                    return_value=[],
                ))
                stack.enter_context(patch.object(
                    mesql_v2, "_list_work_order_release_evidence_cursor",
                    return_value={},
                ))
                stack.enter_context(patch.object(
                    mesql_v2,
                    "_list_existing_work_order_queue_for_update_cursor",
                    return_value=[],
                ))
            else:
                stack.enter_context(patch.object(
                    mesql_v2, "_prepare_work_order_release_context_cursor",
                    return_value=deepcopy(context),
                ))
            stack.enter_context(patch.object(
                mesql_v2, "_lock_station_queue_scope_cursor",
                return_value={"station_code": "ST-1", "next_queue_rank": 3, "rows": []},
            ))
            stack.enter_context(patch.object(
                mesql_v2, "_insert_work_order_route_release_cursor",
                side_effect=insert_release,
            ))
            stack.enter_context(patch.object(
                mesql_v2, "_insert_route_generated_work_order_operation_cursor",
                side_effect=insert_operation,
            ))
            stack.enter_context(patch.object(
                mesql_v2, "_insert_work_order_operation_route_binding_cursor",
                side_effect=insert_binding,
            ))
            stack.enter_context(patch.object(
                mesql_v2, "_insert_initial_station_queue_cursor",
                side_effect=insert_queue,
            ))
            stack.enter_context(patch.object(
                mesql_v2, "_update_work_order_released_state_cursor",
                side_effect=update_work_order,
            ))
            stack.enter_context(patch.object(
                mesql_v2, "_validate_work_order_release_invariants_cursor",
                side_effect=invariant,
            ))
            stack.enter_context(patch.object(
                mesql_v2, "_work_order_release_response_cursor",
                side_effect=response,
            ))
            with self.assertRaises(RuntimeError):
                mesql_v2._run_work_order_release_transaction(
                    object(), self._request()
                )
            self.assertEqual(failing_connection.rollbacks, 1)
            self.assertEqual(failing_connection.commits, 0)
            self.assertEqual(state, {
                "release": 0, "operations": 0, "bindings": 0,
                "queue": 0, "status": "planned",
            })
            attempt["value"] = 2
            counters.update({"operation": 0, "binding": 0})
            result = mesql_v2._run_work_order_release_transaction(
                object(), self._request()
            )
        self.assertTrue(result["released"])
        self.assertEqual(retry_connection.commits, 1)
        self.assertEqual(retry_connection.rollbacks, 0)
        self.assertEqual(state, {
            "release": 1, "operations": 2, "bindings": 2,
            "queue": 1, "status": "queued",
        })


def _make_writer_validation_test(changes, expected_detail):
    def test(self):
        kwargs = self._base_kwargs()
        kwargs.update(changes)
        with patch.object(
            mesql_v2, "database_connection",
            side_effect=AssertionError("database opened before validation"),
        ) as connection_factory:
            with self.assertRaises(mesql_v2.MesqlV2Error) as error:
                mesql_v2.release_work_order_to_route(object(), **kwargs)
        self.assertEqual(error.exception.detail, expected_detail)
        connection_factory.assert_not_called()
    return test


_WRITER_VALIDATION_CASES = {
    "release_id_blank": ({"release_id": " "}, "RELEASE_ID_REQUIRED"),
    "release_id_none": ({"release_id": None}, "RELEASE_ID_INVALID"),
    "work_order_blank": ({"work_order_id": ""}, "WORK_ORDER_ID_REQUIRED"),
    "work_order_none": ({"work_order_id": None}, "WORK_ORDER_ID_INVALID"),
    "route_code_blank": ({"route_code": " "}, "ROUTE_CODE_REQUIRED"),
    "route_code_none": ({"route_code": None}, "ROUTE_CODE_INVALID"),
    "version_zero": ({"route_version": 0}, "ROUTE_VERSION_INVALID"),
    "version_negative": ({"route_version": -1}, "ROUTE_VERSION_INVALID"),
    "version_bool": ({"route_version": True}, "ROUTE_VERSION_INVALID"),
    "version_string": ({"route_version": "2"}, "ROUTE_VERSION_INVALID"),
    "source_blank": ({"release_source": ""}, "RELEASE_SOURCE_REQUIRED"),
    "source_ferp": ({"release_source": "ferp"}, "WORK_ORDER_RELEASE_MODE_NOT_ENABLED"),
    "source_mesql": ({"release_source": "mesql"}, "WORK_ORDER_RELEASE_MODE_NOT_ENABLED"),
    "actor_blank": ({"released_by": " "}, "RELEASED_BY_REQUIRED"),
    "actor_none": ({"released_by": None}, "RELEASED_BY_INVALID"),
    "explicit_mode": ({"mode": "explicit_existing_operation_mapping"}, "WORK_ORDER_RELEASE_MODE_NOT_ENABLED"),
    "unknown_mode": ({"mode": "legacy"}, "RELEASE_MODE_INVALID"),
    "mapping_nonempty": ({"operation_bindings": [{"x": 1}]}, "OPERATION_BINDINGS_NOT_ALLOWED"),
    "mapping_tuple": ({"operation_bindings": ()}, "OPERATION_BINDINGS_NOT_ALLOWED"),
    "metadata_list": ({"metadata": []}, "RELEASE_METADATA_INVALID"),
    "metadata_set": ({"metadata": {"bad": {1, 2}}}, "RELEASE_METADATA_INVALID"),
    "metadata_nan": ({"metadata": {"bad": float("nan")}}, "RELEASE_METADATA_INVALID"),
}

for _name, (_changes, _detail) in _WRITER_VALIDATION_CASES.items():
    setattr(
        WorkOrderReleaseWriterTests,
        f"test_validation_{_name}",
        _make_writer_validation_test(_changes, _detail),
    )


_WRITER_CONFLICT_CASES = {
    "release_id_other_order": "WORK_ORDER_ROUTE_RELEASE_ID_CONFLICT",
    "already_released": "WORK_ORDER_ROUTE_ALREADY_RELEASED",
    "route_code": "WORK_ORDER_ROUTE_VERSION_CONFLICT",
    "route_version": "WORK_ORDER_ROUTE_VERSION_CONFLICT",
    "mode": "WORK_ORDER_RELEASE_MODE_CONFLICT",
    "source": "WORK_ORDER_ROUTE_RELEASE_ID_CONFLICT",
    "actor": "WORK_ORDER_ROUTE_RELEASE_ID_CONFLICT",
    "metadata": "WORK_ORDER_ROUTE_RELEASE_ID_CONFLICT",
    "operation_count": "WORK_ORDER_RELEASE_OPERATION_COUNT_MISMATCH",
    "missing_operation": "WORK_ORDER_RELEASE_OPERATION_COUNT_MISMATCH",
    "static_operation": "WORK_ORDER_RELEASE_OPERATION_SNAPSHOT_MISMATCH",
    "partial_binding": "WORK_ORDER_RELEASE_PARTIAL_BINDING_CONFLICT",
    "mapping": "WORK_ORDER_RELEASE_MAPPING_CONFLICT",
    "digest": "WORK_ORDER_RELEASE_MAPPING_CONFLICT",
    "queue_missing": "WORK_ORDER_RELEASE_QUEUE_CONFLICT",
    "queue_extra": "WORK_ORDER_RELEASE_QUEUE_CONFLICT",
    "queue_identity": "WORK_ORDER_RELEASE_QUEUE_CONFLICT",
}

for _scenario, _detail in _WRITER_CONFLICT_CASES.items():
    setattr(
        WorkOrderReleaseWriterTests,
        f"test_conflict_{_scenario}",
        lambda self, scenario=_scenario, detail=_detail: self._run_conflict_case(
            scenario, detail
        ),
    )


for _scenario in (
    "work_order_status", "operation_status", "actual_quantities",
    "operation_timestamps", "queue_status", "queue_rank", "queue_timestamp",
):
    setattr(
        WorkOrderReleaseWriterTests,
        f"test_replay_ignores_{_scenario}",
        lambda self, scenario=_scenario: self._run_mutable_replay_case(scenario),
    )


for _sqlstate in ("23503", "40P01", "40001", "08006", "XX000"):
    setattr(
        WorkOrderReleaseWriterTests,
        f"test_nonunique_{_sqlstate.lower()}_propagates",
        lambda self, sqlstate=_sqlstate: self._run_nonunique_error_case(sqlstate),
    )


for _failure_point in (
    "after_work_order_lock", "after_route_validation", "after_release_insert",
    "after_first_lifecycle_insert", "after_all_lifecycle_inserts",
    "after_first_binding", "after_all_bindings", "after_queue_insert",
    "after_work_order_update", "before_invariant_validation",
    "before_snapshot_read", "before_transaction_exit",
):
    setattr(
        WorkOrderReleaseWriterTests,
        f"test_rollback_{_failure_point}",
        lambda self, point=_failure_point: self._run_failure_case(point),
    )


def _make_sql_contract_test(constant_name, required, forbidden=()):
    def test(self):
        sql = getattr(mesql_v2, constant_name).lower()
        for fragment in required:
            self.assertIn(fragment.lower(), sql)
        for fragment in forbidden:
            self.assertNotIn(fragment.lower(), sql)
    return test


_RELEASE_SQL_CONTRACTS = {
    "work_order_lock": ("SELECT_WORK_ORDER_FOR_RELEASE_CURSOR_SQL", ("select", "for update", "%(work_order_id)s"), ("select *",)),
    "release_dual_lock": ("SELECT_RELEASES_FOR_UPDATE_CURSOR_SQL", ("order by release_pk", "for update", " or release_id"), ("select *",)),
    "operation_uuid_lock_order": ("SELECT_EXISTING_WORK_ORDER_OPERATIONS_FOR_UPDATE_CURSOR_SQL", ("order by work_order_operation_id", "for update"), ("select *",)),
    "binding_lifecycle_join": ("SELECT_EXISTING_RELEASE_BINDINGS_FOR_UPDATE_CURSOR_SQL", ("join mes.work_order_operations", "operation.order_id", "for update of binding"), ("select *",)),
    "evidence_order_scope": ("SELECT_WORK_ORDER_RELEASE_EVIDENCE_CURSOR_SQL", ("work_order_id = %(work_order_id)s",), ("select *",)),
    "initial_queue_identity": ("SELECT_INITIAL_QUEUE_FOR_UPDATE_CURSOR_SQL", ("order_id = %(work_order_id)s", "work_order_operation_id = %(work_order_operation_id)s::uuid"), ("station_code =",)),
    "queue_advisory_lock": ("LOCK_STATION_QUEUE_ADVISORY_CURSOR_SQL", ("pg_advisory_xact_lock", "hashtextextended", "%(station_code)s"), ("ready",)),
    "station_rows_pk_order": ("SELECT_STATION_QUEUE_FOR_UPDATE_CURSOR_SQL", ("order by station_queue_pk", "for update"), ("select *",)),
    "rank_active_predicate": ("SELECT_NEXT_STATION_QUEUE_RANK_CURSOR_SQL", ("max(queue_rank) + 1", "pending_approval"), ("ready",)),
    "release_plain_insert": ("INSERT_WORK_ORDER_ROUTE_RELEASE_CURSOR_SQL", ("insert into", "returning"), ("on conflict", "update mes")),
    "operation_plain_insert": ("INSERT_ROUTE_GENERATED_WORK_ORDER_OPERATION_CURSOR_SQL", ("insert into", "null", "returning"), ("on conflict", "do update")),
    "binding_plain_insert": ("INSERT_WORK_ORDER_OPERATION_ROUTE_BINDING_CURSOR_SQL", ("insert into", "returning"), ("on conflict",)),
    "queue_plain_insert": ("INSERT_INITIAL_STATION_QUEUE_CURSOR_SQL", ("insert into", "work_order_operation_id", "returning"), ("on conflict",)),
    "work_order_narrow_update": ("UPDATE_WORK_ORDER_RELEASED_STATE_CURSOR_SQL", ("set status = 'queued'", "updated_at = now()"), ("payload =", "metadata =")),
    "exact_route_no_lock": ("SELECT_EXACT_PROCESS_ROUTE_SQL", ("route_code = %(route_code)s", "version = %(route_version)s"), ("for update", "active = true", "max(")),
    "route_item_no_lock": ("SELECT_ITEM_BY_CODE_SQL", ("item_code = %(item_code)s",), ("for update", "select *")),
    "route_operations_exact_join": ("SELECT_PROCESS_ROUTE_OPERATIONS_SQL", ("route.route_id = %(process_route_id)s", "operation.sequence_no"), ("active = true", "limit 1")),
    "release_insert_explicit_columns": ("INSERT_WORK_ORDER_ROUTE_RELEASE_CURSOR_SQL", ("release_id, order_id, process_route_id", "operation_set_digest"), ("select *",)),
    "operation_insert_explicit_columns": ("INSERT_ROUTE_GENERATED_WORK_ORDER_OPERATION_CURSOR_SQL", ("mesql_work_order_operation_id", "planned_quantity", "metadata"), ("select *",)),
    "binding_insert_exact_actor": ("INSERT_WORK_ORDER_OPERATION_ROUTE_BINDING_CURSOR_SQL", ("binding_source", "bound_by", "metadata"), ("select *",)),
    "queue_insert_explicit_identity": ("INSERT_INITIAL_STATION_QUEUE_CURSOR_SQL", ("station_code, order_id, queue_rank", "work_order_operation_id"), ("select *",)),
    "release_lock_read_only": ("SELECT_RELEASES_FOR_UPDATE_CURSOR_SQL", ("select",), ("insert", "update mes.", "delete")),
    "operation_lock_read_only": ("SELECT_EXISTING_WORK_ORDER_OPERATIONS_FOR_UPDATE_CURSOR_SQL", ("select",), ("insert", "delete")),
    "binding_lock_read_only": ("SELECT_EXISTING_RELEASE_BINDINGS_FOR_UPDATE_CURSOR_SQL", ("select",), ("insert", "delete")),
    "queue_lock_read_only": ("SELECT_STATION_QUEUE_FOR_UPDATE_CURSOR_SQL", ("select",), ("insert", "delete")),
}

for _name, (_constant, _required, _forbidden) in _RELEASE_SQL_CONTRACTS.items():
    setattr(
        WorkOrderReleasePrimitiveTests,
        f"test_sql_contract_{_name}",
        _make_sql_contract_test(_constant, _required, _forbidden),
    )


class _BridgeCursor:
    def __init__(self, *, one=None, all_rows=None) -> None:
        self.one = list(one or [])
        self.all_rows = list(all_rows or [])
        self.executed: list[tuple[str, dict]] = []

    def execute(self, sql, params=None) -> None:
        self.executed.append((sql, dict(params or {})))

    def fetchone(self):
        return self.one.pop(0) if self.one else None

    def fetchall(self):
        return self.all_rows.pop(0) if self.all_rows else []


class CompletionBridgePrimitiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.release_id = "RELEASE-5G-A-001"
        self.order_id = "WO-5G-A-001"
        self.route_ids = ["ROP-10", "ROP-20"]
        self.operation_ids = [
            mesql_v2._derive_work_order_release_operation_id(
                self.release_id, route_operation_id
            )
            for route_operation_id in self.route_ids
        ]
        self.operations = [
            self._operation(0, status="queued"),
            self._operation(1, status="planned"),
        ]
        self.bindings = [self._binding(0), self._binding(1)]
        self.release = {
            "release_pk": 1,
            "release_id": self.release_id,
            "order_id": self.order_id,
            "process_route_id": "ROUTE-ID-V2",
            "route_code": "ROUTE-V2",
            "route_version": 2,
            "release_mode": "route_generated",
            "release_source": "local_planning",
            "released_by": "planner",
            "released_at": "2026-07-15T10:00:00+00:00",
            "route_operation_count": 2,
            "metadata": {},
            "created_at": "2026-07-15T10:00:00+00:00",
        }
        self.release["operation_set_digest"] = (
            mesql_v2._compute_work_order_release_operation_set_digest(
                process_route_id=self.release["process_route_id"],
                route_code=self.release["route_code"],
                route_version=self.release["route_version"],
                release_mode=self.release["release_mode"],
                pairs=[
                    {
                        "sequence_no": operation["sequence_no"],
                        "route_operation_id": binding["route_operation_id"],
                        "work_order_operation_id": operation["work_order_operation_id"],
                    }
                    for operation, binding in zip(self.operations, self.bindings)
                ],
            )
        )
        self.runtime = {
            "work_order_operation_id": self.operation_ids[0],
            "work_order_id": self.order_id,
            "station_code": "ST-10",
            "operation_code": "OP-10",
            "execution_status": "closed",
            "closed_at": "2026-07-15T11:00:00+00:00",
            "metadata": {"route_operation_id": self.route_ids[0]},
        }
        self.work_order = {
            "order_id": self.order_id,
            "status": "queued",
            "completed_at": None,
            "payload": {"keep": True},
            "metadata": {"keep": True},
        }
        initial = mesql_v2._build_initial_queue_snapshot(
            release_id=self.release_id,
            operation_snapshot=self.operations[0],
            queue_rank=4,
        )
        self.initial_queue = {
            "station_queue_pk": 10,
            **initial,
            "created_at": "2026-07-15T10:00:00+00:00",
            "updated_at": "2026-07-15T10:00:00+00:00",
        }

    def _operation(self, index, *, status):
        sequence = (index + 1) * 10
        return {
            "work_order_operation_id": self.operation_ids[index],
            "order_id": self.order_id,
            "mesql_work_order_operation_id": None,
            "operation_no": sequence,
            "operation_code": f"OP-{sequence}",
            "operation_name": f"Operation {sequence}",
            "sequence_no": sequence,
            "station_code": f"ST-{sequence}",
            "status": status,
            "planned_quantity": 1,
            "good_quantity": 0,
            "scrap_quantity": 0,
            "uom_code": "EA",
            "started_at": None,
            "completed_at": None,
            "payload": {},
            "metadata": {
                "source": "work_order_release",
                "release_id": self.release_id,
                "process_route_id": "ROUTE-ID-V2",
                "route_code": "ROUTE-V2",
                "route_version": 2,
                "route_operation_id": self.route_ids[index],
            },
            "created_at": None,
            "updated_at": None,
        }

    def _binding(self, index):
        return {
            "binding_pk": index + 1,
            "binding_id": mesql_v2._derive_work_order_release_binding_id(
                self.release_id, self.route_ids[index]
            ),
            "work_order_operation_id": self.operation_ids[index],
            "route_operation_id": self.route_ids[index],
            "binding_source": "work_order_release",
            "bound_by": "planner",
            "bound_at": None,
            "metadata": {"release_id": self.release_id},
            "created_at": None,
        }

    def _error(self, detail, callback):
        with self.assertRaises(mesql_v2.MesqlV2Error) as error:
            callback()
        self.assertEqual(error.exception.detail, detail)

    def _classify(self, **changes):
        values = {
            "work_order": deepcopy(self.work_order),
            "release": deepcopy(self.release),
            "lifecycle_operations": deepcopy(self.operations),
            "bindings": deepcopy(self.bindings),
            "runtime_state": deepcopy(self.runtime),
            "station_queue_rows": [deepcopy(self.initial_queue)],
            "current_work_order_operation_id": self.operation_ids[0],
        }
        values.update(changes)
        return mesql_v2._classify_completion_bridge_state(**values)

    def test_applicability_query_maps_json_safe_values(self):
        cursor = _BridgeCursor(one=[{
            "work_order_operation_id": UUID(self.operation_ids[0]),
            "order_id": self.order_id,
            "operation_code": "OP-10",
            "sequence_no": 10,
            "station_code": "ST-10",
            "status": "queued",
            "completed_at": datetime(2026, 7, 15, 11, 0, 0),
            "payload": {},
            "metadata": {"source": "work_order_release", "release_id": self.release_id},
        }])
        row = mesql_v2._select_completion_bridge_applicability_cursor(
            cursor, self.operation_ids[0]
        )
        self.assertEqual(row["work_order_operation_id"], self.operation_ids[0])
        self.assertEqual(row["completed_at"], "2026-07-15T11:00:00")
        self.assertEqual(len(cursor.executed), 1)

    def test_applicability_missing_row_is_none(self):
        self.assertIsNone(mesql_v2._select_completion_bridge_applicability_cursor(
            _BridgeCursor(), self.operation_ids[0]
        ))

    def test_applicability_exact_marker_is_true(self):
        self.assertTrue(mesql_v2._is_completion_bridge_applicable({
            "metadata": {"source": "work_order_release", "release_id": " Mixed-Id "}
        }))

    def test_applicability_empty_metadata_is_false(self):
        self.assertFalse(mesql_v2._is_completion_bridge_applicable({"metadata": {}}))

    def test_applicability_legacy_source_is_false(self):
        self.assertFalse(mesql_v2._is_completion_bridge_applicable({
            "metadata": {"source": "mesql"}
        }))

    def test_schema_readiness_both_tables(self):
        cursor = _BridgeCursor(one=[(True, True)])
        self.assertEqual(
            mesql_v2._get_completion_bridge_schema_readiness_cursor(cursor),
            {"release_table_ready": True, "binding_table_ready": True, "ready": True},
        )

    def test_schema_readiness_validator_uses_503(self):
        with self.assertRaises(mesql_v2.MesqlV2Error) as error:
            mesql_v2._validate_completion_bridge_schema_readiness({"ready": False})
        self.assertEqual((error.exception.detail, error.exception.status_code), (
            "RUNTIME_COMPLETION_BRIDGE_SCHEMA_NOT_READY", 503
        ))

    def test_station_lock_set_is_unique_lexical_and_case_preserved(self):
        source = ["z", "A"]
        result = mesql_v2._normalize_completion_bridge_station_lock_set(*source)
        self.assertEqual(result, ["A", "z"])
        self.assertEqual(source, ["z", "A"])

    def test_same_station_locks_once(self):
        cursor = _BridgeCursor(one=[None])
        stations = mesql_v2._normalize_completion_bridge_station_lock_set("ST", "ST")
        self.assertEqual(mesql_v2._lock_completion_bridge_station_scopes_cursor(cursor, stations), ["ST"])
        self.assertEqual(len(cursor.executed), 1)

    def test_exact_queue_distinguishes_missing_exact_duplicate(self):
        kwargs = {
            "work_order_id": self.order_id,
            "work_order_operation_id": self.operation_ids[0],
            "station_code": "ST-10",
        }
        self.assertEqual(mesql_v2._select_exact_completion_bridge_queue([], **kwargs)["classification"], "missing")
        self.assertEqual(mesql_v2._select_exact_completion_bridge_queue([self.initial_queue], **kwargs)["classification"], "exact")
        self.assertEqual(mesql_v2._select_exact_completion_bridge_queue([self.initial_queue, deepcopy(self.initial_queue)], **kwargs)["classification"], "duplicate")

    def test_next_rank_exact_three_statuses(self):
        rows = [
            {"station_code": "ST", "status": status, "queue_rank": rank}
            for rank, status in enumerate(("queued", "ready", "active", "pending_approval", "completed"), 1)
        ]
        self.assertEqual(mesql_v2._compute_completion_bridge_next_queue_rank(rows, "ST"), 5)

    def test_identity_valid_complete_set(self):
        mesql_v2._validate_completion_bridge_release_identity(self.release, self.operations)
        mesql_v2._validate_completion_bridge_binding_set(self.release, self.operations, self.bindings)
        self.assertEqual(
            mesql_v2._recompute_completion_bridge_operation_set_digest(
                self.release, self.operations, self.bindings
            ),
            self.release["operation_set_digest"],
        )

    def test_runtime_identity_valid(self):
        mesql_v2._validate_completion_bridge_runtime_identity(
            self.runtime, self.operations[0], self.bindings[0]
        )

    def test_successor_resolves_terminal_row(self):
        operations = deepcopy(self.operations)
        operations[1]["status"] = "completed"
        self.assertEqual(
            mesql_v2._resolve_completion_bridge_successor(operations, self.operation_ids[0])["work_order_operation_id"],
            self.operation_ids[1],
        )

    def test_successor_final_is_none(self):
        self.assertIsNone(mesql_v2._resolve_completion_bridge_successor(
            self.operations, self.operation_ids[1]
        ))

    def test_classifier_first_nonfinal(self):
        result = self._classify()
        self.assertEqual(result["classification"], "first_bridge")
        self.assertFalse(result["final_operation"])

    def test_classifier_immediate_replay(self):
        operations = deepcopy(self.operations)
        operations[0].update(status="completed", completed_at=self.runtime["closed_at"])
        current_queue = deepcopy(self.initial_queue)
        current_queue["status"] = "completed"
        successor_queue = mesql_v2._build_completion_bridge_successor_queue_snapshot(
            release=self.release,
            predecessor_operation=operations[0],
            successor_operation=operations[1],
            queue_rank=7,
        )
        successor_queue["station_queue_pk"] = 11
        operations[1]["status"] = "queued"
        result = self._classify(
            lifecycle_operations=operations,
            station_queue_rows=[current_queue, successor_queue],
        )
        self.assertEqual(result["classification"], "exact_replay")

    def _single_final_context(self, *, replay=False):
        operation = deepcopy(self.operations[1])
        operation["status"] = "completed" if replay else "active"
        operation["completed_at"] = self.runtime["closed_at"] if replay else None
        binding = deepcopy(self.bindings[1])
        release = deepcopy(self.release)
        release["route_operation_count"] = 1
        release["operation_set_digest"] = mesql_v2._compute_work_order_release_operation_set_digest(
            process_route_id=release["process_route_id"],
            route_code=release["route_code"],
            route_version=release["route_version"],
            release_mode=release["release_mode"],
            pairs=[{
                "sequence_no": operation["sequence_no"],
                "route_operation_id": binding["route_operation_id"],
                "work_order_operation_id": operation["work_order_operation_id"],
            }],
        )
        runtime = deepcopy(self.runtime)
        runtime.update({
            "work_order_operation_id": operation["work_order_operation_id"],
            "station_code": operation["station_code"],
            "operation_code": operation["operation_code"],
            "metadata": {"route_operation_id": binding["route_operation_id"]},
        })
        work_order = deepcopy(self.work_order)
        if replay:
            work_order.update(status="completed", completed_at=runtime["closed_at"])
        queue = mesql_v2._build_initial_queue_snapshot(
            release_id=release["release_id"], operation_snapshot=operation, queue_rank=3
        )
        queue.update(station_queue_pk=30, status="completed" if replay else "active")
        return {
            "work_order": work_order,
            "release": release,
            "lifecycle_operations": [operation],
            "bindings": [binding],
            "runtime_state": runtime,
            "station_queue_rows": [queue],
            "current_work_order_operation_id": operation["work_order_operation_id"],
        }

    def test_classifier_first_final_bridge(self):
        result = mesql_v2._classify_completion_bridge_state(
            **self._single_final_context()
        )
        self.assertEqual((result["classification"], result["final_operation"]), (
            "first_bridge", True
        ))

    def test_classifier_exact_final_replay(self):
        result = mesql_v2._classify_completion_bridge_state(
            **self._single_final_context(replay=True)
        )
        self.assertEqual(result["classification"], "exact_replay")

    def test_classifier_final_timestamp_conflict(self):
        context = self._single_final_context(replay=True)
        context["work_order"]["completed_at"] = "2026-07-15T12:00:00+00:00"
        self._error(
            "RUNTIME_COMPLETION_BRIDGE_WORK_ORDER_CONFLICT",
            lambda: mesql_v2._classify_completion_bridge_state(**context),
        )

    def test_classifier_partial_current_state_conflict(self):
        operations = deepcopy(self.operations)
        operations[0]["status"] = "completed"
        operations[0]["completed_at"] = None
        self._error(
            "RUNTIME_COMPLETION_BRIDGE_OPERATION_STATE_CONFLICT",
            lambda: self._classify(lifecycle_operations=operations),
        )

    def test_classifier_premature_successor_conflict(self):
        operations = deepcopy(self.operations)
        operations[1]["status"] = "queued"
        self._error(
            "RUNTIME_COMPLETION_BRIDGE_SUCCESSOR_CONFLICT",
            lambda: self._classify(lifecycle_operations=operations),
        )

    def test_classifier_missing_current_queue_conflict(self):
        self._error(
            "RUNTIME_COMPLETION_BRIDGE_QUEUE_CONFLICT",
            lambda: self._classify(station_queue_rows=[]),
        )

    def test_classifier_duplicate_current_queue_conflict(self):
        self._error(
            "RUNTIME_COMPLETION_BRIDGE_QUEUE_CONFLICT",
            lambda: self._classify(station_queue_rows=[
                deepcopy(self.initial_queue), deepcopy(self.initial_queue)
            ]),
        )

    def _progressed_replay(self, lifecycle_status, queue_status):
        operations = deepcopy(self.operations)
        operations[0].update(status="completed", completed_at=self.runtime["closed_at"])
        operations[1]["status"] = lifecycle_status
        if lifecycle_status == "completed":
            operations[1]["completed_at"] = "2026-07-15T12:00:00+00:00"
        current_queue = deepcopy(self.initial_queue)
        current_queue["status"] = "completed"
        successor_queue = mesql_v2._build_completion_bridge_successor_queue_snapshot(
            release=self.release, predecessor_operation=operations[0],
            successor_operation=operations[1], queue_rank=7,
        )
        successor_queue.update(station_queue_pk=11, status=queue_status)
        result = self._classify(
            lifecycle_operations=operations,
            station_queue_rows=[current_queue, successor_queue],
        )
        self.assertEqual(result["classification"], "exact_replay")

    def test_replay_after_successor_queued(self):
        self._progressed_replay("queued", "queued")

    def test_replay_after_successor_active(self):
        self._progressed_replay("active", "active")

    def test_replay_after_successor_completed(self):
        self._progressed_replay("completed", "completed")

    def test_work_order_lock_mapper_uses_dict_rows(self):
        row = {
            "work_order_pk": 1, "order_id": self.order_id, "erp_type": "production",
            "status": "queued", "product_code": "ITEM", "target_quantity": Decimal("1.5"),
            "started_at": None, "completed_at": None, "source_system": "mes_web",
            "source_file": None, "external_ref": None, "payload": {}, "metadata": {},
            "created_at": datetime(2026, 7, 15), "updated_at": datetime(2026, 7, 15),
        }
        result = mesql_v2._select_completion_bridge_work_order_for_update_cursor(
            _BridgeCursor(one=[row]), self.order_id
        )
        self.assertEqual(result["target_quantity"], 1.5)
        self.assertEqual(result["created_at"], "2026-07-15T00:00:00")

    def test_release_lock_rejects_duplicate_rows(self):
        self._error(
            "RUNTIME_COMPLETION_BRIDGE_RELEASE_CONFLICT",
            lambda: mesql_v2._select_completion_bridge_release_for_update_cursor(
                _BridgeCursor(all_rows=[[self.release, deepcopy(self.release)]]), self.order_id
            ),
        )

    def test_binding_lock_is_lifecycle_join_scoped(self):
        cursor = _BridgeCursor(all_rows=[[self.bindings[0]]])
        result = mesql_v2._list_completion_bridge_bindings_for_update_cursor(
            cursor, self.order_id
        )
        self.assertEqual(result[0]["work_order_operation_id"], self.operation_ids[0])
        self.assertEqual(cursor.executed[0][1], {"work_order_id": self.order_id})

    def test_execution_state_lock_mapper_includes_pk(self):
        row = {
            "execution_state_pk": 9, "execution_state_id": "STATE-1",
            **self.runtime, "operation_completion_policy": "auto_close_on_required_steps",
            "current_step_code": None, "started_at": None, "evidence_completed_at": None,
            "pending_final_approval_at": None, "last_event_id": None,
            "last_approval_id": None, "created_at": None, "updated_at": None,
        }
        result = mesql_v2._select_completion_bridge_execution_state_for_update_cursor(
            _BridgeCursor(one=[row]), self.operation_ids[0]
        )
        self.assertEqual(result["execution_state_pk"], 9)

    def test_runtime_step_lock_mapper_includes_pk(self):
        row = {
            "work_order_operation_step_pk": 5, "work_order_operation_step_id": "STEP-1",
            "work_order_operation_id": self.operation_ids[0], "work_order_id": self.order_id,
            "operation_code": "OP-10", "step_code": "S1", "step_no": 1,
            "station_code": "ST-10", "status": "completed", "started_at": None,
            "completed_at": datetime(2026, 7, 15), "started_by_event_id": None,
            "completed_by_event_id": "E1", "required_for_completion": True,
            "records_duration": True, "approval_required_after_finish": False,
            "created_at": None, "updated_at": None, "metadata": {},
        }
        result = mesql_v2._list_completion_bridge_runtime_steps_for_update_cursor(
            _BridgeCursor(all_rows=[[row]]), self.operation_ids[0]
        )
        self.assertEqual(result[0]["work_order_operation_step_pk"], 5)
        self.assertEqual(result[0]["completed_at"], "2026-07-15T00:00:00")

    def test_station_queue_lock_normalizes_without_mutation(self):
        stations = ["ST-20", "ST-10", "ST-20"]
        cursor = _BridgeCursor(all_rows=[[self.initial_queue]])
        result = mesql_v2._list_completion_bridge_station_queue_rows_for_update_cursor(
            cursor, stations
        )
        self.assertEqual(stations, ["ST-20", "ST-10", "ST-20"])
        self.assertEqual(cursor.executed[0][1]["station_codes"], ["ST-10", "ST-20"])
        self.assertEqual(result[0]["station_queue_pk"], 10)

    def test_successor_lifecycle_write_is_guarded(self):
        cursor = _BridgeCursor(one=[self.operations[1]])
        result = mesql_v2._queue_successor_lifecycle_cursor(
            cursor, work_order_operation_id=self.operation_ids[1]
        )
        self.assertEqual(result["work_order_operation_id"], self.operation_ids[1])
        self.assertEqual(cursor.executed[0][1], {"work_order_operation_id": self.operation_ids[1]})

    def test_successor_queue_insert_uses_jsonb_payload_and_metadata(self):
        snapshot = mesql_v2._build_completion_bridge_successor_queue_snapshot(
            release=self.release, predecessor_operation=self.operations[0],
            successor_operation=self.operations[1], queue_rank=8,
        )
        returned = {"station_queue_pk": 12, **snapshot, "created_at": None, "updated_at": None}
        cursor = _BridgeCursor(one=[returned])
        result = mesql_v2._insert_completion_bridge_successor_queue_cursor(cursor, snapshot)
        self.assertEqual(result["source"], "runtime_completion_bridge")
        self.assertNotIn("source", cursor.executed[0][1])
        self.assertEqual(_unwrap_json_value(cursor.executed[0][1]["metadata"]), snapshot["metadata"])

    def test_work_order_completion_write_maps_timestamp(self):
        row = {"work_order_pk": 1, **self.work_order, "erp_type": "production",
               "product_code": "ITEM", "target_quantity": 1, "started_at": None,
               "source_system": "mes_web", "source_file": None, "external_ref": None,
               "created_at": None, "updated_at": None}
        row.update(status="completed", completed_at=self.runtime["closed_at"])
        result = mesql_v2._complete_work_order_from_runtime_cursor(
            _BridgeCursor(one=[row]), work_order_id=self.order_id,
            closed_at=self.runtime["closed_at"],
        )
        self.assertEqual(result["completed_at"], self.runtime["closed_at"])

    def _snapshot_work_order_row(self, *, status="queued", completed_at=None):
        return {
            "work_order_pk": 1, "order_id": self.order_id,
            "erp_type": "production", "status": status,
            "product_code": "ITEM", "target_quantity": Decimal("1.5"),
            "started_at": None, "completed_at": completed_at,
            "source_system": "mes_web", "source_file": None,
            "external_ref": None, "payload": {"keep": True},
            "metadata": {"keep": True}, "created_at": datetime(2026, 7, 15),
            "updated_at": datetime(2026, 7, 15),
        }

    def _snapshot_execution_row(self):
        return {
            "execution_state_id": "STATE-1", **self.runtime,
            "operation_completion_policy": "auto_close_on_required_steps",
            "current_step_code": None, "started_at": None,
            "evidence_completed_at": self.runtime["closed_at"],
            "pending_final_approval_at": None, "last_event_id": "EVENT-1",
            "last_approval_id": None, "created_at": datetime(2026, 7, 15),
            "updated_at": datetime(2026, 7, 15),
        }

    def test_snapshot_nonfinal_shape_and_exact_scoping(self):
        completed = deepcopy(self.operations[0])
        completed.update(status="completed", completed_at=self.runtime["closed_at"])
        current_queue = deepcopy(self.initial_queue)
        current_queue["status"] = "completed"
        successor = deepcopy(self.operations[1])
        successor["status"] = "queued"
        successor_queue = mesql_v2._build_completion_bridge_successor_queue_snapshot(
            release=self.release, predecessor_operation=completed,
            successor_operation=successor, queue_rank=8,
        )
        successor_queue.update(station_queue_pk=11, created_at=None, updated_at=None)
        cursor = _BridgeCursor(
            one=[self._snapshot_execution_row(), completed, successor, self._snapshot_work_order_row()],
            all_rows=[[current_queue], [successor_queue]],
        )
        result = mesql_v2._read_completion_bridge_snapshot_cursor(
            cursor, work_order_id=self.order_id,
            completed_work_order_operation_id=self.operation_ids[0],
            successor_work_order_operation_id=self.operation_ids[1],
        )
        self.assertEqual(set(result), {
            "execution_state", "completed_operation", "completed_queue",
            "successor_operation", "successor_queue", "work_order",
        })
        self.assertEqual(result["work_order"]["target_quantity"], 1.5)
        for _sql, params in cursor.executed[1:5]:
            if "work_order_id" in params:
                self.assertEqual(params["work_order_id"], self.order_id)

    def test_snapshot_final_shape_uses_none_successor(self):
        completed = deepcopy(self.operations[0])
        completed.update(status="completed", completed_at=self.runtime["closed_at"])
        current_queue = deepcopy(self.initial_queue)
        current_queue["status"] = "completed"
        cursor = _BridgeCursor(
            one=[self._snapshot_execution_row(), completed,
                 self._snapshot_work_order_row(status="completed", completed_at=self.runtime["closed_at"])],
            all_rows=[[current_queue]],
        )
        result = mesql_v2._read_completion_bridge_snapshot_cursor(
            cursor, work_order_id=self.order_id,
            completed_work_order_operation_id=self.operation_ids[0],
        )
        self.assertIsNone(result["successor_operation"])
        self.assertIsNone(result["successor_queue"])
        self.assertEqual(len(cursor.executed), 4)

    def test_snapshot_duplicate_exact_queue_is_conflict(self):
        completed = deepcopy(self.operations[0])
        cursor = _BridgeCursor(
            one=[self._snapshot_execution_row(), completed],
            all_rows=[[self.initial_queue, deepcopy(self.initial_queue)]],
        )
        self._error(
            "RUNTIME_COMPLETION_BRIDGE_QUEUE_CONFLICT",
            lambda: mesql_v2._read_completion_bridge_snapshot_cursor(
                cursor, work_order_id=self.order_id,
                completed_work_order_operation_id=self.operation_ids[0],
            ),
        )

    def test_first_write_invariants_validate_authoritative_nonfinal_snapshot(self):
        expected = self._classify()
        completed = deepcopy(self.operations[0])
        completed.update(status="completed", completed_at=self.runtime["closed_at"])
        completed_queue = deepcopy(self.initial_queue)
        completed_queue["status"] = "completed"
        successor = deepcopy(self.operations[1])
        successor["status"] = "queued"
        successor_queue = mesql_v2._build_completion_bridge_successor_queue_snapshot(
            release=self.release, predecessor_operation=completed,
            successor_operation=successor, queue_rank=8,
        )
        successor_queue.update(station_queue_pk=11, created_at=None, updated_at=None)
        cursor = _BridgeCursor(
            one=[self._snapshot_execution_row(), completed, successor, self._snapshot_work_order_row()],
            all_rows=[[completed_queue], [successor_queue]],
        )
        snapshot = mesql_v2._validate_completion_bridge_first_write_invariants_cursor(
            cursor, expected
        )
        self.assertEqual(snapshot["completed_operation"]["status"], "completed")
        self.assertEqual(snapshot["successor_operation"]["status"], "queued")

    def test_successor_queue_snapshot_does_not_mutate_inputs(self):
        release = deepcopy(self.release)
        predecessor = deepcopy(self.operations[0])
        successor = deepcopy(self.operations[1])
        before = deepcopy((release, predecessor, successor))
        snapshot = mesql_v2._build_completion_bridge_successor_queue_snapshot(
            release=release, predecessor_operation=predecessor,
            successor_operation=successor, queue_rank=8,
        )
        self.assertEqual((release, predecessor, successor), before)
        self.assertEqual(snapshot["source"], "runtime_completion_bridge")
        self.assertEqual(set(snapshot["metadata"]), {
            "source", "release_id", "predecessor_work_order_operation_id"
        })

    def test_write_primitives_use_exact_parameters(self):
        cursor = _BridgeCursor(one=[deepcopy(self.operations[0]), deepcopy(self.initial_queue)])
        mesql_v2._complete_lifecycle_operation_from_runtime_cursor(
            cursor, work_order_operation_id=self.operation_ids[0],
            closed_at=self.runtime["closed_at"],
        )
        mesql_v2._complete_current_queue_from_runtime_cursor(cursor, station_queue_pk=10)
        self.assertEqual(cursor.executed[0][1]["work_order_operation_id"], self.operation_ids[0])
        self.assertEqual(cursor.executed[1][1], {"station_queue_pk": 10})

    def test_private_primitives_open_no_connections(self):
        for name in (
            "_select_completion_bridge_applicability_cursor",
            "_get_completion_bridge_schema_readiness_cursor",
            "_select_completion_bridge_work_order_for_update_cursor",
            "_complete_lifecycle_operation_from_runtime_cursor",
            "_read_completion_bridge_snapshot_cursor",
        ):
            source = inspect.getsource(getattr(mesql_v2, name))
            self.assertNotIn("database_connection", source)
            self.assertNotIn(".commit(", source)
            self.assertNotIn(".rollback(", source)

    def test_finish_execution_step_uses_private_bridge_integration_only(self):
        source = inspect.getsource(mesql_v2.finish_execution_step)
        self.assertIn("_finish_execution_step_transaction", source)
        self.assertIn("_recover_runtime_completion_bridge_queue_violation", source)
        self.assertNotIn("database_connection", source)


def _make_bridge_marker_error_test(metadata):
    def test(self):
        self._error(
            "RUNTIME_COMPLETION_BRIDGE_IDENTITY_CONFLICT",
            lambda: mesql_v2._is_completion_bridge_applicable({"metadata": deepcopy(metadata)}),
        )
    return test


for _name, _metadata in {
    "missing_release": {"source": "work_order_release"},
    "blank_release": {"source": "work_order_release", "release_id": " "},
    "missing_source": {"release_id": "REL"},
    "wrong_source_with_release": {"source": "MESQL", "release_id": "REL"},
    "source_none": {"source": None, "release_id": "REL"},
    "release_nonstring": {"source": "work_order_release", "release_id": 1},
}.items():
    setattr(CompletionBridgePrimitiveTests, f"test_marker_error_{_name}", _make_bridge_marker_error_test(_metadata))


def _completion_bridge_preflight_pair(test_case):
    preflight = deepcopy(test_case.operations[0])
    authoritative = deepcopy(test_case.operations[0])
    return preflight, authoritative


def _test_preflight_revalidation_accepts_exact_identity(self):
    preflight, authoritative = _completion_bridge_preflight_pair(self)
    self.assertIsNone(mesql_v2._compare_completion_bridge_preflight_identity(
        preflight, authoritative
    ))


setattr(
    CompletionBridgePrimitiveTests,
    "test_preflight_revalidation_accepts_exact_identity",
    _test_preflight_revalidation_accepts_exact_identity,
)


def _make_preflight_progression_ignored_test(field_name, before, after):
    def test(self):
        preflight, authoritative = _completion_bridge_preflight_pair(self)
        preflight[field_name] = deepcopy(before)
        authoritative[field_name] = deepcopy(after)
        mesql_v2._compare_completion_bridge_preflight_identity(
            preflight, authoritative
        )
    return test


for _name, _field_name, _before, _after in (
    ("status", "status", "queued", "completed"),
    ("completed_at", "completed_at", None, "2026-07-15T11:00:00+00:00"),
    ("work_order_status", "work_order_status", "queued", "completed"),
    ("queue_status", "queue_status", "queued", "completed"),
    ("runtime_status", "runtime_status", "active", "closed"),
):
    setattr(
        CompletionBridgePrimitiveTests,
        f"test_preflight_progression_ignored_{_name}",
        _make_preflight_progression_ignored_test(
            _field_name, _before, _after
        ),
    )


def _test_preflight_status_and_completed_at_progression_are_ignored(self):
    preflight, authoritative = _completion_bridge_preflight_pair(self)
    authoritative.update(
        status="completed",
        completed_at="2026-07-15T11:00:00+00:00",
    )
    mesql_v2._compare_completion_bridge_preflight_identity(
        preflight, authoritative
    )


def _test_preflight_nonmarker_metadata_is_not_identity(self):
    preflight, authoritative = _completion_bridge_preflight_pair(self)
    preflight["metadata"]["diagnostic"] = "before"
    authoritative["metadata"]["diagnostic"] = "after"
    mesql_v2._compare_completion_bridge_preflight_identity(
        preflight, authoritative
    )


setattr(
    CompletionBridgePrimitiveTests,
    "test_preflight_status_and_completed_at_progression_are_ignored",
    _test_preflight_status_and_completed_at_progression_are_ignored,
)
setattr(
    CompletionBridgePrimitiveTests,
    "test_preflight_nonmarker_metadata_is_not_identity",
    _test_preflight_nonmarker_metadata_is_not_identity,
)


def _make_preflight_identity_mismatch_test(field_name, value):
    def test(self):
        preflight, authoritative = _completion_bridge_preflight_pair(self)
        authoritative[field_name] = value
        self._error(
            "RUNTIME_COMPLETION_BRIDGE_IDENTITY_CONFLICT",
            lambda: mesql_v2._compare_completion_bridge_preflight_identity(
                preflight, authoritative
            ),
        )
    return test


for _name, _field_name, _value in (
    ("lifecycle_uuid", "work_order_operation_id", "00000000-0000-0000-0000-000000000000"),
    ("order", "order_id", "WO-OTHER"),
    ("operation_code", "operation_code", "OP-OTHER"),
    ("sequence", "sequence_no", 20),
    ("station", "station_code", "ST-OTHER"),
):
    setattr(
        CompletionBridgePrimitiveTests,
        f"test_preflight_identity_mismatch_{_name}",
        _make_preflight_identity_mismatch_test(_field_name, _value),
    )


def _make_preflight_marker_mismatch_test(field_name, value):
    def test(self):
        preflight, authoritative = _completion_bridge_preflight_pair(self)
        authoritative["metadata"][field_name] = value
        self._error(
            "RUNTIME_COMPLETION_BRIDGE_IDENTITY_CONFLICT",
            lambda: mesql_v2._compare_completion_bridge_preflight_identity(
                preflight, authoritative
            ),
        )
    return test


for _name, _field_name, _value in (
    ("source", "source", "WORK_ORDER_RELEASE"),
    ("release_id", "release_id", "release-5g-a-001"),
):
    setattr(
        CompletionBridgePrimitiveTests,
        f"test_preflight_marker_mismatch_{_name}",
        _make_preflight_marker_mismatch_test(_field_name, _value),
    )


def _make_preflight_malformed_marker_test(target, metadata):
    def test(self):
        preflight, authoritative = _completion_bridge_preflight_pair(self)
        if target == "preflight":
            preflight["metadata"] = deepcopy(metadata)
        else:
            authoritative["metadata"] = deepcopy(metadata)
        self._error(
            "RUNTIME_COMPLETION_BRIDGE_IDENTITY_CONFLICT",
            lambda: mesql_v2._compare_completion_bridge_preflight_identity(
                preflight, authoritative
            ),
        )
    return test


for _name, _target, _metadata in (
    ("preflight_removed", "preflight", {}),
    ("authoritative_removed", "authoritative", {}),
    ("authoritative_missing_release", "authoritative", {"source": "work_order_release"}),
    ("authoritative_missing_source", "authoritative", {"release_id": "REL"}),
    ("authoritative_blank_release", "authoritative", {"source": "work_order_release", "release_id": " "}),
    ("authoritative_non_object", "authoritative", None),
):
    setattr(
        CompletionBridgePrimitiveTests,
        f"test_preflight_malformed_marker_{_name}",
        _make_preflight_malformed_marker_test(_target, _metadata),
    )


def _make_bridge_readiness_test(row, expected):
    def test(self):
        self.assertEqual(
            mesql_v2._get_completion_bridge_schema_readiness_cursor(_BridgeCursor(one=[row])),
            expected,
        )
    return test


for _name, _row, _expected in (
    ("release_absent", (False, True), {"release_table_ready": False, "binding_table_ready": True, "ready": False}),
    ("binding_absent", (True, False), {"release_table_ready": True, "binding_table_ready": False, "ready": False}),
    ("both_absent", (False, False), {"release_table_ready": False, "binding_table_ready": False, "ready": False}),
    ("dict_row", {"release_table_ready": True, "binding_table_ready": True}, {"release_table_ready": True, "binding_table_ready": True, "ready": True}),
):
    setattr(CompletionBridgePrimitiveTests, f"test_readiness_{_name}", _make_bridge_readiness_test(_row, _expected))


_BRIDGE_SQL_CONTRACTS = {
    "applicability": ("SELECT_COMPLETION_BRIDGE_APPLICABILITY_CURSOR_SQL", ("work_order_operation_id = %(work_order_operation_id)s::uuid", "metadata"), ("for update", "work_order_route_releases", "route_bindings", "select *")),
    "schema_catalog": ("SELECT_COMPLETION_BRIDGE_SCHEMA_READINESS_CURSOR_SQL", ("to_regclass('mes.work_order_route_releases')", "to_regclass('mes.work_order_operation_route_bindings')"), ("from mes.work_order_route", "for update", "select *")),
    "work_order_lock": ("SELECT_COMPLETION_BRIDGE_WORK_ORDER_FOR_UPDATE_CURSOR_SQL", ("order_id = %(work_order_id)s", "for update"), ("select *",)),
    "release_lock": ("SELECT_COMPLETION_BRIDGE_RELEASE_FOR_UPDATE_CURSOR_SQL", ("order by release_pk", "for update"), ("select *", " or ")),
    "lifecycle_lock": ("SELECT_COMPLETION_BRIDGE_OPERATIONS_FOR_UPDATE_CURSOR_SQL", ("order by work_order_operation_id", "for update"), ("select *",)),
    "binding_lock": ("SELECT_COMPLETION_BRIDGE_BINDINGS_FOR_UPDATE_CURSOR_SQL", ("join mes.work_order_operations", "order by binding.binding_pk", "for update of binding"), ("select *",)),
    "execution_lock": ("SELECT_COMPLETION_BRIDGE_EXECUTION_STATE_FOR_UPDATE_CURSOR_SQL", ("execution_state_pk", "for update"), ("select *",)),
    "steps_lock": ("SELECT_COMPLETION_BRIDGE_RUNTIME_STEPS_FOR_UPDATE_CURSOR_SQL", ("order by step_no", "for update"), ("select *",)),
    "station_lock": ("LOCK_COMPLETION_BRIDGE_STATION_SCOPE_CURSOR_SQL", ("pg_advisory_xact_lock", "mes:work_order_release:station_queue:", "%(station_code)s"), ("commit",)),
    "queue_lock": ("SELECT_COMPLETION_BRIDGE_STATION_QUEUE_ROWS_FOR_UPDATE_CURSOR_SQL", ("any(%(station_codes)s)", "order by station_code asc, station_queue_pk asc", "for update"), ("select *",)),
    "lifecycle_update": ("UPDATE_COMPLETION_BRIDGE_LIFECYCLE_CURSOR_SQL", ("status = 'completed'", "completed_at = %(closed_at)s", "returning"), ("payload =", "metadata =", "good_quantity =", "scrap_quantity =")),
    "queue_update": ("UPDATE_COMPLETION_BRIDGE_CURRENT_QUEUE_CURSOR_SQL", ("status = 'completed'", "station_queue_pk = %(station_queue_pk)s", "returning"), ("queue_rank =", "payload =", "metadata =")),
    "successor_update": ("UPDATE_COMPLETION_BRIDGE_SUCCESSOR_LIFECYCLE_CURSOR_SQL", ("status = 'queued'", "status = 'planned'", "returning"), ("on conflict",)),
    "successor_insert": ("INSERT_COMPLETION_BRIDGE_SUCCESSOR_QUEUE_CURSOR_SQL", ("runtime_completion_bridge", "work_order_operation_id", "returning"), ("on conflict", "route_operation_id")),
    "work_order_update": ("UPDATE_COMPLETION_BRIDGE_WORK_ORDER_CURSOR_SQL", ("status = 'completed'", "completed_at = %(closed_at)s", "returning"), ("payload =", "metadata =", "started_at =")),
    "snapshot_operation": ("SELECT_COMPLETION_BRIDGE_OPERATION_CURSOR_SQL", ("order_id = %(work_order_id)s", "work_order_operation_id = %(work_order_operation_id)s::uuid"), ("for update", "select *")),
    "snapshot_queue": ("SELECT_COMPLETION_BRIDGE_QUEUE_CURSOR_SQL", ("order_id = %(work_order_id)s", "work_order_operation_id = %(work_order_operation_id)s::uuid"), ("for update", "select *")),
    "snapshot_order": ("SELECT_COMPLETION_BRIDGE_WORK_ORDER_CURSOR_SQL", ("order_id = %(work_order_id)s",), ("for update", "select *")),
}

for _name, (_constant, _required, _forbidden) in _BRIDGE_SQL_CONTRACTS.items():
    setattr(
        CompletionBridgePrimitiveTests,
        f"test_bridge_sql_{_name}",
        _make_sql_contract_test(_constant, _required, _forbidden),
    )


def _make_identity_mutation_test(target, field, value, expected_detail):
    def test(self):
        release = deepcopy(self.release)
        operations = deepcopy(self.operations)
        bindings = deepcopy(self.bindings)
        if target == "release":
            release[field] = value
            callback = lambda: mesql_v2._validate_completion_bridge_release_identity(release, operations)
        elif target == "operation":
            operations[1][field] = value
            callback = lambda: mesql_v2._validate_completion_bridge_release_identity(release, operations)
        elif target == "operation_metadata":
            operations[1]["metadata"][field] = value
            callback = lambda: mesql_v2._validate_completion_bridge_release_identity(release, operations)
        else:
            bindings[1][field] = value
            callback = lambda: mesql_v2._validate_completion_bridge_binding_set(release, operations, bindings)
        self._error(expected_detail, callback)
    return test


for _name, _target, _field, _value, _detail in (
    ("count", "release", "route_operation_count", 3, "RUNTIME_COMPLETION_BRIDGE_RELEASE_CONFLICT"),
    ("mode", "release", "release_mode", "explicit_existing_operation_mapping", "RUNTIME_COMPLETION_BRIDGE_RELEASE_CONFLICT"),
    ("sequence_duplicate", "operation", "sequence_no", 10, "RUNTIME_COMPLETION_BRIDGE_SEQUENCE_CONFLICT"),
    ("sequence_zero", "operation", "sequence_no", 0, "RUNTIME_COMPLETION_BRIDGE_SEQUENCE_CONFLICT"),
    ("sequence_bool", "operation", "sequence_no", True, "RUNTIME_COMPLETION_BRIDGE_SEQUENCE_CONFLICT"),
    ("foreign_order", "operation", "order_id", "WO-FOREIGN", "RUNTIME_COMPLETION_BRIDGE_IDENTITY_CONFLICT"),
    ("route_code", "operation_metadata", "route_code", "OTHER", "RUNTIME_COMPLETION_BRIDGE_IDENTITY_CONFLICT"),
    ("release_id", "operation_metadata", "release_id", "OTHER", "RUNTIME_COMPLETION_BRIDGE_IDENTITY_CONFLICT"),
    ("binding_source", "binding", "binding_source", "manual_setup", "RUNTIME_COMPLETION_BRIDGE_BINDING_CONFLICT"),
    ("binding_route", "binding", "route_operation_id", "OTHER", "RUNTIME_COMPLETION_BRIDGE_BINDING_CONFLICT"),
    ("binding_id", "binding", "binding_id", "OTHER", "RUNTIME_COMPLETION_BRIDGE_BINDING_CONFLICT"),
    ("binding_operation", "binding", "work_order_operation_id", "00000000-0000-0000-0000-000000000000", "RUNTIME_COMPLETION_BRIDGE_BINDING_CONFLICT"),
):
    setattr(
        CompletionBridgePrimitiveTests,
        f"test_identity_error_{_name}",
        _make_identity_mutation_test(_target, _field, _value, _detail),
    )


def _make_runtime_identity_error_test(field, value, detail):
    def test(self):
        runtime = deepcopy(self.runtime)
        if field.startswith("metadata."):
            runtime["metadata"][field.split(".", 1)[1]] = value
        else:
            runtime[field] = value
        self._error(detail, lambda: mesql_v2._validate_completion_bridge_runtime_identity(
            runtime, self.operations[0], self.bindings[0]
        ))
    return test


for _name, _field, _value, _detail in (
    ("not_closed", "execution_status", "active", "RUNTIME_COMPLETION_BRIDGE_RUNTIME_NOT_CLOSED"),
    ("missing_closed_at", "closed_at", None, "RUNTIME_COMPLETION_BRIDGE_RUNTIME_NOT_CLOSED"),
    ("order", "work_order_id", "OTHER", "RUNTIME_COMPLETION_BRIDGE_IDENTITY_CONFLICT"),
    ("uuid", "work_order_operation_id", "00000000-0000-0000-0000-000000000000", "RUNTIME_COMPLETION_BRIDGE_IDENTITY_CONFLICT"),
    ("code", "operation_code", "OTHER", "RUNTIME_COMPLETION_BRIDGE_IDENTITY_CONFLICT"),
    ("station", "station_code", "OTHER", "RUNTIME_COMPLETION_BRIDGE_IDENTITY_CONFLICT"),
    ("binding", "metadata.route_operation_id", "OTHER", "RUNTIME_COMPLETION_BRIDGE_IDENTITY_CONFLICT"),
):
    setattr(
        CompletionBridgePrimitiveTests,
        f"test_runtime_identity_error_{_name}",
        _make_runtime_identity_error_test(_field, _value, _detail),
    )


def _make_rank_status_test(status, included):
    def test(self):
        rows = [{"station_code": "ST", "status": status, "queue_rank": 9}]
        self.assertEqual(
            mesql_v2._compute_completion_bridge_next_queue_rank(rows, "ST"),
            10 if included else 0,
        )
    return test


for _status, _included in (
    ("queued", True), ("active", True), ("pending_approval", True),
    ("ready", False), ("completed", False), ("cancelled", False),
):
    setattr(
        CompletionBridgePrimitiveTests,
        f"test_rank_status_{_status}",
        _make_rank_status_test(_status, _included),
    )


class CompletionBridgeIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        fixture = CompletionBridgePrimitiveTests(methodName="runTest")
        fixture.setUp()
        self.fixture = fixture

    def _nested_bridge(self, bridged=True):
        return {
            "bridged": bridged,
            "execution_state": {"execution_status": "closed"},
            "completed_operation": {"status": "completed"},
            "completed_queue": {"status": "completed"},
            "successor_operation": {"status": "queued"},
            "successor_queue": {"status": "queued", "queue_rank": 8},
            "work_order": {"status": "queued"},
        }

    def _call(
        self,
        connection,
        *,
        applicable=False,
        apply_result=None,
        apply_error=None,
        external_event_id="finish-event-001",
    ):
        applicability = {
            "work_order_operation_id": "11111111-1111-1111-1111-111111111111",
            "order_id": "WO-E2E-MAVI-001",
            "operation_code": "OP10_ASSEMBLY_CLASSIFICATION",
            "sequence_no": 10,
            "station_code": "ASSEMBLY_01",
            "status": "active",
            "completed_at": None,
            "payload": {},
            "metadata": (
                {"source": "work_order_release", "release_id": "REL-1"}
                if applicable else {}
            ),
        }
        context = {
            "work_order": {"order_id": "WO-E2E-MAVI-001", "status": "queued"},
            "release": {"order_id": "WO-E2E-MAVI-001"},
            "lifecycle_operations": [],
            "bindings": [],
            "execution_state": mesql_v2._json_safe(deepcopy(connection.cursor_instance.execution_state_row)),
            "runtime_steps": mesql_v2._json_safe(deepcopy(connection.cursor_instance.execution_step_rows)),
        }

        @contextmanager
        def fake_connection(_config):
            yield connection

        with ExitStack() as stack:
            stack.enter_context(patch.object(mesql_v2, "database_connection", fake_connection))
            stack.enter_context(patch.object(
                mesql_v2, "_select_completion_bridge_applicability_cursor",
                return_value=applicability,
            ))
            if applicable:
                stack.enter_context(patch.object(
                    mesql_v2, "_get_completion_bridge_schema_readiness_cursor",
                    return_value={
                        "release_table_ready": True,
                        "binding_table_ready": True,
                        "ready": True,
                    },
                ))
                stack.enter_context(patch.object(
                    mesql_v2, "_prepare_runtime_completion_bridge_cursor",
                    return_value=context,
                ))
                apply_mock = stack.enter_context(patch.object(
                    mesql_v2, "_apply_runtime_completion_bridge_cursor",
                    return_value=(apply_result or self._nested_bridge()),
                    side_effect=apply_error,
                ))
            else:
                apply_mock = stack.enter_context(patch.object(
                    mesql_v2, "_apply_runtime_completion_bridge_cursor",
                    side_effect=AssertionError("legacy bridge apply"),
                ))
            result = mesql_v2.finish_execution_step(
                AppConfig(db_enabled=True),
                work_order_operation_id="11111111-1111-1111-1111-111111111111",
                step_code="COLOR_SENSOR_ENTRY_EVIDENCE",
                event_source="COLOR_SENSOR_ENTRY",
                external_event_id=external_event_id,
            )
        return result, apply_mock

    def test_legacy_response_adds_none_without_sidecar_access(self):
        connection = _Connection()
        _seed_finishable_execution_step(connection.cursor_instance)
        result, apply_mock = self._call(connection)
        self.assertIsNone(result["completion_bridge"])
        apply_mock.assert_not_called()
        sql = "\n".join(item[0].lower() for item in connection.cursor_instance.executed)
        self.assertNotIn("work_order_route_releases", sql)
        self.assertNotIn("work_order_operation_route_bindings", sql)
        self.assertNotIn("to_regclass", sql)

    def test_first_closed_bridge_returns_true_authoritative_object(self):
        connection = _Connection()
        _seed_finishable_execution_step(
            connection.cursor_instance, include_next_step=False,
            operation_completion_policy="auto_close_on_required_steps",
        )
        nested = self._nested_bridge(True)
        result, apply_mock = self._call(
            connection, applicable=True, apply_result=nested
        )
        self.assertTrue(result["finished"])
        self.assertTrue(result["event_inserted"])
        self.assertEqual(result["completion_bridge"], nested)
        apply_mock.assert_called_once()

    def test_nonclosed_marker_path_returns_none(self):
        connection = _Connection()
        _seed_finishable_execution_step(connection.cursor_instance)
        result, apply_mock = self._call(connection, applicable=True)
        self.assertEqual(result["execution_state"]["execution_status"], "active")
        self.assertIsNone(result["completion_bridge"])
        apply_mock.assert_not_called()

    def test_supported_closed_duplicate_reaches_replay(self):
        connection = _Connection()
        _seed_finishable_execution_step(
            connection.cursor_instance, include_next_step=False,
            operation_completion_policy="auto_close_on_required_steps",
            step_status="completed",
        )
        closed_at = datetime(2026, 7, 15, 12, 0, 0)
        connection.cursor_instance.execution_state_row.update({
            "execution_status": "closed",
            "closed_at": closed_at,
            "evidence_completed_at": closed_at,
        })
        connection.cursor_instance.operation_event_rows = [
            _fake_operation_event(
                event_type="step_finish", external_event_id="finish-event-001"
            )
        ]
        nested = self._nested_bridge(False)
        result, apply_mock = self._call(
            connection, applicable=True, apply_result=nested
        )
        self.assertFalse(result["finished"])
        self.assertFalse(result["event_inserted"])
        self.assertFalse(result["completion_bridge"]["bridged"])
        apply_mock.assert_called_once()
        self.assertEqual(connection.cursor_instance.operation_event_rows.__len__(), 1)

    def test_schema_not_ready_precedes_event_write(self):
        connection = _Connection()
        _seed_finishable_execution_step(connection.cursor_instance)

        @contextmanager
        def fake_connection(_config):
            yield connection

        marker = {"metadata": {"source": "work_order_release", "release_id": "REL"}}
        with patch.object(mesql_v2, "database_connection", fake_connection), patch.object(
            mesql_v2, "_select_completion_bridge_applicability_cursor", return_value=marker
        ), patch.object(
            mesql_v2, "_get_completion_bridge_schema_readiness_cursor",
            return_value={"release_table_ready": False, "binding_table_ready": True, "ready": False},
        ):
            with self.assertRaises(mesql_v2.MesqlV2Error) as error:
                mesql_v2.finish_execution_step(
                    AppConfig(db_enabled=True),
                    work_order_operation_id="11111111-1111-1111-1111-111111111111",
                    step_code="COLOR_SENSOR_ENTRY_EVIDENCE",
                    event_source="COLOR_SENSOR_ENTRY",
                    external_event_id="finish-event-001",
                )
        self.assertEqual(error.exception.detail, "RUNTIME_COMPLETION_BRIDGE_SCHEMA_NOT_READY")
        self.assertEqual(connection.cursor_instance.operation_event_rows, [])

    def test_unexplained_undefined_table_propagates(self):
        connection = _Connection()
        _seed_finishable_execution_step(connection.cursor_instance)
        undefined = UndefinedTable("unexplained")

        @contextmanager
        def fake_connection(_config):
            yield connection

        marker = {"metadata": {"source": "work_order_release", "release_id": "REL"}}
        with patch.object(mesql_v2, "database_connection", fake_connection), patch.object(
            mesql_v2, "_select_completion_bridge_applicability_cursor", return_value=marker
        ), patch.object(
            mesql_v2, "_get_completion_bridge_schema_readiness_cursor", side_effect=undefined
        ):
            with self.assertRaises(UndefinedTable) as error:
                mesql_v2.finish_execution_step(
                    AppConfig(db_enabled=True),
                    work_order_operation_id="11111111-1111-1111-1111-111111111111",
                    step_code="COLOR_SENSOR_ENTRY_EVIDENCE",
                    event_source="COLOR_SENSOR_ENTRY",
                    external_event_id="finish-event-001",
                )
        self.assertIs(error.exception, undefined)

    def test_bridge_conflict_rolls_back_event_and_runtime(self):
        connection = _Connection()
        _seed_finishable_execution_step(
            connection.cursor_instance, include_next_step=False,
            operation_completion_policy="auto_close_on_required_steps",
        )
        before_state = deepcopy(connection.cursor_instance.execution_state_row)
        before_steps = deepcopy(connection.cursor_instance.execution_step_rows)
        with self.assertRaises(mesql_v2.MesqlV2Error):
            self._call(
                connection, applicable=True,
                apply_error=mesql_v2.MesqlV2Error(
                    "RUNTIME_COMPLETION_BRIDGE_QUEUE_CONFLICT", status_code=409
                ),
            )
        self.assertFalse(connection.committed)
        self.assertTrue(connection.transaction_rolled_back)
        self.assertEqual(connection.cursor_instance.operation_event_rows, [])
        self.assertEqual(connection.cursor_instance.execution_state_row, before_state)
        self.assertEqual(connection.cursor_instance.execution_step_rows, before_steps)

    def test_prepare_lock_prefix_is_normative(self):
        fx = self.fixture
        applicability = {
            name: deepcopy(fx.operations[0].get(name))
            for name in (
                "work_order_operation_id", "order_id", "operation_code",
                "sequence_no", "station_code", "status", "completed_at",
                "payload", "metadata",
            )
        }
        order = []
        state = {"execution_state_pk": 1, **deepcopy(fx.runtime)}
        state["execution_status"] = "active"
        state["closed_at"] = None
        with ExitStack() as stack:
            for name, value, label in (
                ("_select_completion_bridge_work_order_for_update_cursor", fx.work_order, "work_order"),
                ("_select_completion_bridge_release_for_update_cursor", fx.release, "release"),
                ("_list_completion_bridge_operations_for_update_cursor", fx.operations, "operations"),
                ("_list_completion_bridge_bindings_for_update_cursor", fx.bindings, "bindings"),
                ("_select_completion_bridge_execution_state_for_update_cursor", state, "execution"),
                ("_list_completion_bridge_runtime_steps_for_update_cursor", [], "steps"),
            ):
                stack.enter_context(patch.object(
                    mesql_v2, name,
                    side_effect=lambda *_args, value=value, label=label: (
                        order.append(label), deepcopy(value)
                    )[1],
                ))
            result = mesql_v2._prepare_runtime_completion_bridge_cursor(
                object(), applicability=applicability
            )
        self.assertEqual(order, [
            "work_order", "release", "operations", "bindings", "execution", "steps"
        ])
        self.assertNotIn("execution_state_pk", result["execution_state"])

    def test_exact_replay_takes_no_advisory_or_write(self):
        fx = self.fixture
        context = {
            "work_order": fx.work_order,
            "release": fx.release,
            "lifecycle_operations": deepcopy(fx.operations),
            "bindings": fx.bindings,
        }
        context["lifecycle_operations"][0].update(
            status="completed", completed_at=fx.runtime["closed_at"]
        )
        snapshot = {"execution_state": fx.runtime, "completed_operation": {},
                    "completed_queue": {}, "successor_operation": {},
                    "successor_queue": {}, "work_order": fx.work_order}
        with patch.object(
            mesql_v2, "_completion_bridge_replay_queue_rows_cursor", return_value=[]
        ), patch.object(
            mesql_v2, "_classify_completion_bridge_state",
            return_value={"classification": "exact_replay"},
        ), patch.object(
            mesql_v2, "_read_completion_bridge_snapshot_cursor", return_value=snapshot
        ), patch.object(
            mesql_v2, "_lock_completion_bridge_station_scopes_cursor"
        ) as station_lock, patch.object(
            mesql_v2, "_complete_lifecycle_operation_from_runtime_cursor"
        ) as lifecycle_write:
            result = mesql_v2._apply_runtime_completion_bridge_cursor(
                object(), work_order_operation_id=fx.operation_ids[0],
                locked_context=context, runtime_state=fx.runtime,
            )
        self.assertFalse(result["bridged"])
        station_lock.assert_not_called()
        lifecycle_write.assert_not_called()

    def test_queue_conflict_evidence_exact_predicates(self):
        recovery = {
            "constraint_name": "uq_mes_station_queue_station_active_rank",
            "station_code": "ST", "queue_rank": 4, "order_id": "WO",
            "successor_work_order_operation_id": "OP",
        }
        self.assertTrue(mesql_v2._completion_bridge_queue_conflict_evidence(
            [{"station_code": "ST", "queue_rank": 4, "status": "active"}], recovery
        ))
        self.assertFalse(mesql_v2._completion_bridge_queue_conflict_evidence(
            [{"station_code": "ST", "queue_rank": 4, "status": "ready"}], recovery
        ))

    def test_public_signature_is_unchanged_and_has_no_bridge_parameter(self):
        self.assertEqual(list(inspect.signature(mesql_v2.finish_execution_step).parameters), [
            "config", "work_order_operation_id", "step_code", "event_source",
            "external_event_id", "idempotency_key", "actor_id", "payload",
        ])


def _make_legacy_completion_bridge_none_test(policy, include_next):
    def test(self):
        connection = _Connection()
        _seed_finishable_execution_step(
            connection.cursor_instance,
            include_next_step=include_next,
            operation_completion_policy=policy,
        )
        result, apply_mock = self._call(connection)
        self.assertIn("completion_bridge", result)
        self.assertIsNone(result["completion_bridge"])
        apply_mock.assert_not_called()
    return test


for _index, (_policy, _include_next) in enumerate(
    (
        ("manual_close", False),
        ("auto_close_on_required_steps", False),
        ("auto_complete_pending_approval", False),
        ("manual_close", True),
        ("auto_close_on_required_steps", True),
        ("auto_complete_pending_approval", True),
    ) * 2
):
    setattr(
        CompletionBridgeIntegrationTests,
        f"test_legacy_none_case_{_index:02d}",
        _make_legacy_completion_bridge_none_test(_policy, _include_next),
    )


def _make_bridge_conflict_rollback_test(detail):
    def test(self):
        connection = _Connection()
        _seed_finishable_execution_step(
            connection.cursor_instance, include_next_step=False,
            operation_completion_policy="auto_close_on_required_steps",
        )
        before = deepcopy(connection.cursor_instance.__dict__)
        with self.assertRaises(mesql_v2.MesqlV2Error) as error:
            self._call(
                connection, applicable=True,
                apply_error=mesql_v2.MesqlV2Error(detail, status_code=409),
            )
        self.assertEqual(error.exception.detail, detail)
        self.assertTrue(connection.transaction_rolled_back)
        self.assertEqual(connection.cursor_instance.operation_event_rows, [])
        self.assertEqual(
            connection.cursor_instance.execution_state_row,
            before["execution_state_row"],
        )
        self.assertEqual(
            connection.cursor_instance.execution_step_rows,
            before["execution_step_rows"],
        )
    return test


for _detail in (
    "RUNTIME_COMPLETION_BRIDGE_RELEASE_CONFLICT",
    "RUNTIME_COMPLETION_BRIDGE_BINDING_CONFLICT",
    "RUNTIME_COMPLETION_BRIDGE_IDENTITY_CONFLICT",
    "RUNTIME_COMPLETION_BRIDGE_SEQUENCE_CONFLICT",
    "RUNTIME_COMPLETION_BRIDGE_OPERATION_STATE_CONFLICT",
    "RUNTIME_COMPLETION_BRIDGE_QUEUE_CONFLICT",
    "RUNTIME_COMPLETION_BRIDGE_SUCCESSOR_CONFLICT",
    "RUNTIME_COMPLETION_BRIDGE_WORK_ORDER_CONFLICT",
):
    setattr(
        CompletionBridgeIntegrationTests,
        f"test_conflict_rollback_{_detail.lower()}",
        _make_bridge_conflict_rollback_test(_detail),
    )


def _make_bridge_failure_injection_test(point):
    def test(self):
        connection = _Connection()
        _seed_finishable_execution_step(
            connection.cursor_instance, include_next_step=False,
            operation_completion_policy="auto_close_on_required_steps",
        )
        before_state = deepcopy(connection.cursor_instance.execution_state_row)
        before_steps = deepcopy(connection.cursor_instance.execution_step_rows)
        with self.assertRaises(RuntimeError) as error:
            self._call(
                connection, applicable=True,
                apply_error=RuntimeError(f"failure:{point}"),
            )
        self.assertEqual(str(error.exception), f"failure:{point}")
        self.assertTrue(connection.transaction_rolled_back)
        self.assertFalse(connection.committed)
        self.assertEqual(connection.cursor_instance.operation_event_rows, [])
        self.assertEqual(connection.cursor_instance.execution_state_row, before_state)
        self.assertEqual(connection.cursor_instance.execution_step_rows, before_steps)
    return test


for _point in (
    "after_finish_event_insert", "after_runtime_step_completion",
    "after_runtime_closed_transition", "after_current_lifecycle_completion",
    "after_current_queue_terminalization", "after_successor_resolution",
    "after_successor_lifecycle_update", "after_all_station_advisory_locks",
    "after_successor_queue_insert", "after_final_work_order_completion",
    "before_invariant_validation", "before_authoritative_snapshot",
    "before_transaction_exit",
):
    setattr(
        CompletionBridgeIntegrationTests,
        f"test_failure_injection_{_point}",
        _make_bridge_failure_injection_test(_point),
    )


def _make_response_field_preservation_test(field_name):
    def test(self):
        connection = _Connection()
        _seed_finishable_execution_step(
            connection.cursor_instance, include_next_step=False,
            operation_completion_policy="auto_close_on_required_steps",
        )
        result, _apply = self._call(connection, applicable=True)
        self.assertIn(field_name, result)
        self.assertIn("completion_bridge", result)
    return test


for _field_name in (
    "status", "work_order_operation_id", "station_code", "step_code",
    "finished", "event_inserted", "implicit_started", "event",
    "execution_state", "step", "next_step", "completion_policy_applied",
    "completion_policy", "execution_transition", "required_steps_completed",
):
    setattr(
        CompletionBridgeIntegrationTests,
        f"test_response_preserves_{_field_name}",
        _make_response_field_preservation_test(_field_name),
    )


def _make_queue_evidence_test(constraint, row, expected):
    def test(self):
        recovery = {
            "constraint_name": constraint,
            "station_code": "ST", "queue_rank": 4, "order_id": "WO",
            "successor_work_order_operation_id": "OP",
        }
        self.assertIs(
            mesql_v2._completion_bridge_queue_conflict_evidence([deepcopy(row)], recovery),
            expected,
        )
    return test


for _name, _constraint, _row, _expected in (
    ("rank_queued", "uq_mes_station_queue_station_active_rank", {"station_code": "ST", "queue_rank": 4, "status": "queued"}, True),
    ("rank_active", "uq_mes_station_queue_station_active_rank", {"station_code": "ST", "queue_rank": 4, "status": "active"}, True),
    ("rank_pending", "uq_mes_station_queue_station_active_rank", {"station_code": "ST", "queue_rank": 4, "status": "pending_approval"}, True),
    ("rank_ready", "uq_mes_station_queue_station_active_rank", {"station_code": "ST", "queue_rank": 4, "status": "ready"}, False),
    ("rank_other", "uq_mes_station_queue_station_active_rank", {"station_code": "ST", "queue_rank": 5, "status": "active"}, False),
    ("order_exact", "uq_mes_station_queue_station_order", {"station_code": "ST", "order_id": "WO"}, True),
    ("order_other", "uq_mes_station_queue_station_order", {"station_code": "ST", "order_id": "OTHER"}, False),
    ("operation_exact", "uq_mes_station_queue_station_operation", {"station_code": "ST", "work_order_operation_id": "OP"}, True),
    ("operation_other", "uq_mes_station_queue_station_operation", {"station_code": "ST", "work_order_operation_id": "OTHER"}, False),
    ("foreign_station", "uq_mes_station_queue_station_order", {"station_code": "OTHER", "order_id": "WO"}, False),
):
    setattr(
        CompletionBridgeIntegrationTests,
        f"test_queue_evidence_{_name}",
        _make_queue_evidence_test(_constraint, _row, _expected),
    )


def _make_finish_original_error_propagation_test(error):
    def test(self):
        with patch.object(
            mesql_v2, "_finish_execution_step_transaction", side_effect=error
        ):
            with self.assertRaises(type(error)) as caught:
                mesql_v2.finish_execution_step(
                    object(),
                    work_order_operation_id="11111111-1111-1111-1111-111111111111",
                    step_code="STEP",
                    event_source="SOURCE",
                    external_event_id="event",
                )
        self.assertIs(caught.exception, error)
    return test


for _name, _error in (
    ("foreign_key", _FakePgError("23503")),
    ("deadlock", _FakePgError("40P01")),
    ("serialization", _FakePgError("40001")),
    ("connection", _FakePgError("08006")),
    ("unknown_db", _FakePgError("XX000")),
    ("generic", RuntimeError("generic")),
):
    setattr(
        CompletionBridgeIntegrationTests,
        f"test_finish_propagates_original_{_name}",
        _make_finish_original_error_propagation_test(_error),
    )


def _bridge_first_apply_patches(test_case, insert_error):
    fx = test_case.fixture
    context = {
        "work_order": fx.work_order,
        "release": fx.release,
        "lifecycle_operations": deepcopy(fx.operations),
        "bindings": fx.bindings,
    }
    classified = {
        "classification": "first_bridge",
        "current_operation": context["lifecycle_operations"][0],
        "current_queue": deepcopy(fx.initial_queue),
        "successor_operation": context["lifecycle_operations"][1],
        "successor_queue": None,
        "final_operation": False,
        "runtime_state": fx.runtime,
        "work_order": fx.work_order,
        "release": fx.release,
    }
    stack = ExitStack()
    stack.enter_context(patch.object(
        mesql_v2, "_lock_completion_bridge_station_scopes_cursor"
    ))
    stack.enter_context(patch.object(
        mesql_v2, "_list_completion_bridge_station_queue_rows_for_update_cursor",
        return_value=[deepcopy(fx.initial_queue)],
    ))
    stack.enter_context(patch.object(
        mesql_v2, "_classify_completion_bridge_state", return_value=classified
    ))
    stack.enter_context(patch.object(
        mesql_v2, "_complete_lifecycle_operation_from_runtime_cursor",
        return_value={"status": "completed"},
    ))
    stack.enter_context(patch.object(
        mesql_v2, "_complete_current_queue_from_runtime_cursor",
        return_value={"status": "completed"},
    ))
    stack.enter_context(patch.object(
        mesql_v2, "_queue_successor_lifecycle_cursor",
        return_value={"status": "queued"},
    ))
    stack.enter_context(patch.object(
        mesql_v2, "_insert_completion_bridge_successor_queue_cursor",
        side_effect=insert_error,
    ))
    return stack, context


def _test_apply_wraps_known_queue_23505(self):
    original = _FakePgError("23505", "uq_mes_station_queue_station_active_rank")
    stack, context = _bridge_first_apply_patches(self, original)
    with stack:
        with self.assertRaises(mesql_v2._CompletionBridgeQueueViolation) as error:
            mesql_v2._apply_runtime_completion_bridge_cursor(
                object(),
                work_order_operation_id=self.fixture.operation_ids[0],
                locked_context=context,
                runtime_state=self.fixture.runtime,
            )
    self.assertIs(error.exception.original_error, original)
    self.assertEqual(error.exception.recovery["queue_rank"], 0)


def _test_apply_propagates_unknown_queue_23505(self):
    original = _FakePgError("23505", "uq_unknown")
    stack, context = _bridge_first_apply_patches(self, original)
    with stack:
        with self.assertRaises(_FakePgError) as error:
            mesql_v2._apply_runtime_completion_bridge_cursor(
                object(),
                work_order_operation_id=self.fixture.operation_ids[0],
                locked_context=context,
                runtime_state=self.fixture.runtime,
            )
    self.assertIs(error.exception, original)


setattr(
    CompletionBridgeIntegrationTests,
    "test_apply_wraps_known_queue_23505",
    _test_apply_wraps_known_queue_23505,
)
setattr(
    CompletionBridgeIntegrationTests,
    "test_apply_propagates_unknown_queue_23505",
    _test_apply_propagates_unknown_queue_23505,
)


def _test_queue_recovery_uses_fresh_context_and_maps_evidence(self):
    original = _FakePgError("23505", "uq_mes_station_queue_station_active_rank")
    violation = mesql_v2._CompletionBridgeQueueViolation(
        original,
        {
            "constraint_name": "uq_mes_station_queue_station_active_rank",
            "work_order_operation_id": "11111111-1111-1111-1111-111111111111",
            "order_id": "WO",
            "successor_work_order_operation_id": "22222222-2222-2222-2222-222222222222",
            "station_code": "ST",
            "queue_rank": 4,
        },
    )
    connection = _Connection()
    lifecycle = []

    @contextmanager
    def fresh_connection(_config):
        lifecycle.append("open")
        try:
            yield connection
        finally:
            lifecycle.append("closed")

    with patch.object(mesql_v2, "database_connection", fresh_connection), patch.object(
        mesql_v2, "_select_completion_bridge_applicability_cursor",
        return_value={"metadata": {"source": "work_order_release", "release_id": "REL"}},
    ), patch.object(
        mesql_v2, "_get_completion_bridge_schema_readiness_cursor",
        return_value={"release_table_ready": True, "binding_table_ready": True, "ready": True},
    ), patch.object(
        mesql_v2, "_lock_completion_bridge_station_scopes_cursor"
    ), patch.object(
        mesql_v2, "_list_completion_bridge_station_queue_rows_for_update_cursor",
        return_value=[{"station_code": "ST", "queue_rank": 4, "status": "active"}],
    ):
        with self.assertRaises(mesql_v2.MesqlV2Error) as error:
            mesql_v2._recover_runtime_completion_bridge_queue_violation(
                object(), violation
            )
    self.assertEqual(error.exception.detail, "RUNTIME_COMPLETION_BRIDGE_QUEUE_CONFLICT")
    self.assertEqual(lifecycle, ["open", "closed"])


setattr(
    CompletionBridgeIntegrationTests,
    "test_queue_recovery_uses_fresh_context_and_maps_evidence",
    _test_queue_recovery_uses_fresh_context_and_maps_evidence,
)


def _test_concurrent_duplicate_revalidates_progressed_lifecycle_and_replays(self):
    fx = self.fixture
    shared = {
        "work_order": deepcopy(fx.work_order),
        "release": deepcopy(fx.release),
        "operations": deepcopy(fx.operations),
        "bindings": deepcopy(fx.bindings),
        "queues": [deepcopy(fx.initial_queue)],
        "event_exists": False,
    }
    preflight_barrier = Barrier(2)
    work_order_lock = Lock()
    results = {}
    errors = []
    counters = {
        "event_insert": 0,
        "connection-a": {
            "advisory": 0, "lifecycle": 0, "current_queue": 0,
            "successor": 0, "successor_queue": 0,
        },
        "connection-b": {
            "advisory": 0, "lifecycle": 0, "current_queue": 0,
            "successor": 0, "successor_queue": 0,
        },
    }

    class _ConcurrentCursor:
        def __init__(self, name):
            self.name = name
            self.holds_work_order_lock = False

    def lock_work_order(cursor, work_order_id):
        self.assertEqual(work_order_id, fx.order_id)
        work_order_lock.acquire()
        cursor.holds_work_order_lock = True
        return deepcopy(shared["work_order"])

    def read_release(_cursor, work_order_id):
        self.assertEqual(work_order_id, fx.order_id)
        return deepcopy(shared["release"])

    def read_operations(_cursor, work_order_id):
        self.assertEqual(work_order_id, fx.order_id)
        return deepcopy(shared["operations"])

    def read_bindings(_cursor, work_order_id):
        self.assertEqual(work_order_id, fx.order_id)
        return deepcopy(shared["bindings"])

    def read_execution(_cursor, work_order_operation_id):
        self.assertEqual(work_order_operation_id, fx.operation_ids[0])
        return {"execution_state_pk": 1, **deepcopy(fx.runtime)}

    def read_runtime_steps(_cursor, work_order_operation_id):
        self.assertEqual(work_order_operation_id, fx.operation_ids[0])
        return []

    def lock_stations(cursor, station_codes):
        counters[cursor.name]["advisory"] += 1
        return list(station_codes)

    def read_station_queues(_cursor, _station_codes):
        return deepcopy(shared["queues"])

    def complete_lifecycle(cursor, *, work_order_operation_id, closed_at):
        counters[cursor.name]["lifecycle"] += 1
        operation = next(
            item for item in shared["operations"]
            if item["work_order_operation_id"] == work_order_operation_id
        )
        operation.update(status="completed", completed_at=closed_at)
        return deepcopy(operation)

    def complete_current_queue(cursor, *, station_queue_pk):
        counters[cursor.name]["current_queue"] += 1
        queue = next(
            item for item in shared["queues"]
            if item["station_queue_pk"] == station_queue_pk
        )
        queue["status"] = "completed"
        return deepcopy(queue)

    def queue_successor(cursor, *, work_order_operation_id):
        counters[cursor.name]["successor"] += 1
        operation = next(
            item for item in shared["operations"]
            if item["work_order_operation_id"] == work_order_operation_id
        )
        operation["status"] = "queued"
        return deepcopy(operation)

    def insert_successor_queue(cursor, queue_snapshot):
        counters[cursor.name]["successor_queue"] += 1
        queue = {
            "station_queue_pk": 11,
            **deepcopy(queue_snapshot),
            "created_at": None,
            "updated_at": None,
        }
        shared["queues"].append(queue)
        return deepcopy(queue)

    def read_replay_queues(_cursor, **_kwargs):
        return deepcopy(shared["queues"])

    def read_snapshot(_cursor, **_kwargs):
        return {
            "execution_state": deepcopy(fx.runtime),
            "completed_operation": deepcopy(shared["operations"][0]),
            "completed_queue": deepcopy(shared["queues"][0]),
            "successor_operation": deepcopy(shared["operations"][1]),
            "successor_queue": deepcopy(shared["queues"][1]),
            "work_order": deepcopy(shared["work_order"]),
        }

    def run(cursor):
        applicability = {
            name: deepcopy(fx.operations[0].get(name))
            for name in (
                "work_order_operation_id", "order_id", "operation_code",
                "sequence_no", "station_code", "status", "completed_at",
                "payload", "metadata",
            )
        }
        try:
            preflight_barrier.wait(timeout=5)
            context = mesql_v2._prepare_runtime_completion_bridge_cursor(
                cursor, applicability=applicability
            )
            event_inserted = not shared["event_exists"]
            if event_inserted:
                shared["event_exists"] = True
                counters["event_insert"] += 1
            bridge = mesql_v2._apply_runtime_completion_bridge_cursor(
                cursor,
                work_order_operation_id=fx.operation_ids[0],
                locked_context=context,
                runtime_state=deepcopy(fx.runtime),
            )
            results[cursor.name] = {
                "finished": event_inserted,
                "event_inserted": event_inserted,
                "completion_bridge": bridge,
            }
        except BaseException as error:
            errors.append(error)
        finally:
            if cursor.holds_work_order_lock:
                work_order_lock.release()

    with ExitStack() as stack:
        for name, side_effect in (
            ("_select_completion_bridge_work_order_for_update_cursor", lock_work_order),
            ("_select_completion_bridge_release_for_update_cursor", read_release),
            ("_list_completion_bridge_operations_for_update_cursor", read_operations),
            ("_list_completion_bridge_bindings_for_update_cursor", read_bindings),
            ("_select_completion_bridge_execution_state_for_update_cursor", read_execution),
            ("_list_completion_bridge_runtime_steps_for_update_cursor", read_runtime_steps),
            ("_lock_completion_bridge_station_scopes_cursor", lock_stations),
            ("_list_completion_bridge_station_queue_rows_for_update_cursor", read_station_queues),
            ("_complete_lifecycle_operation_from_runtime_cursor", complete_lifecycle),
            ("_complete_current_queue_from_runtime_cursor", complete_current_queue),
            ("_queue_successor_lifecycle_cursor", queue_successor),
            ("_insert_completion_bridge_successor_queue_cursor", insert_successor_queue),
            ("_completion_bridge_replay_queue_rows_cursor", read_replay_queues),
            ("_read_completion_bridge_snapshot_cursor", read_snapshot),
        ):
            stack.enter_context(patch.object(mesql_v2, name, side_effect=side_effect))
        stack.enter_context(patch.object(
            mesql_v2,
            "_validate_completion_bridge_first_write_invariants_cursor",
            return_value={},
        ))
        threads = [
            Thread(target=run, args=(_ConcurrentCursor(name),), name=name)
            for name in ("connection-a", "connection-b")
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())

    self.assertEqual(errors, [])
    self.assertEqual(counters["event_insert"], 1)
    self.assertEqual(
        sorted(
            (
                result["finished"],
                result["event_inserted"],
                result["completion_bridge"]["bridged"],
            )
            for result in results.values()
        ),
        [(False, False, False), (True, True, True)],
    )
    winner = next(
        name for name, result in results.items()
        if result["completion_bridge"]["bridged"]
    )
    loser = next(name for name in results if name != winner)
    self.assertEqual(counters[winner], {
        "advisory": 1, "lifecycle": 1, "current_queue": 1,
        "successor": 1, "successor_queue": 1,
    })
    self.assertEqual(counters[loser], {
        "advisory": 0, "lifecycle": 0, "current_queue": 0,
        "successor": 0, "successor_queue": 0,
    })
    self.assertEqual(len(shared["queues"]), 2)
    self.assertEqual(shared["operations"][0]["status"], "completed")
    self.assertEqual(shared["operations"][1]["status"], "queued")


setattr(
    CompletionBridgeIntegrationTests,
    "test_concurrent_duplicate_revalidates_progressed_lifecycle_and_replays",
    _test_concurrent_duplicate_revalidates_progressed_lifecycle_and_replays,
)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import mes_web.app as app_module
from mes_web.config import AppConfig
from mes_web.db.mesql_queue import MesqlQueueWriteResult
from mes_web.db.work_order_transition_writer import WorkOrderTransitionWriteResult
from mes_web.mesql_client import MesqlConflictError, MesqlUnavailableError
from mes_web.oee_state import OeeRuntimeStateManager, default_runtime_state
from mes_web.runtime import SnapshotHub
from mes_web.store import DashboardStore


class _ExcelSink:
    def record_work_order_state(self, _state, _received_at: str) -> None:
        return

    def record_kiosk_event(self, _event_type: str, _payload, _received_at: str) -> None:
        return


class _Mqtt:
    def publish_command(self, _payload: str) -> None:
        return


class _Runtime:
    def __init__(self, manager: OeeRuntimeStateManager) -> None:
        self.oee_manager = manager
        self.excel_sink = _ExcelSink()
        self.mqtt_client = _Mqtt()

    async def start(self) -> None:
        return

    async def stop(self) -> None:
        return


class _Mesql:
    def __init__(self, *, unavailable: bool = False, start_conflict: bool = False, complete_conflict: bool = False, completed_good: float = 2) -> None:
        self.unavailable = unavailable
        self.start_conflict = start_conflict
        self.complete_conflict = complete_conflict
        self.completed_good = completed_good
        self.remote_status = "queued"
        self.start_calls: list[dict] = []
        self.complete_calls: list[dict] = []

    def _queue(self, include_done: bool = False) -> dict:
        queue_status = "done" if self.remote_status == "completed" else ("active" if self.remote_status == "in_progress" else "queued")
        if queue_status == "done" and not include_done:
            rows = []
        else:
            rows = [{
                "station_code": "ASSEMBLY_01",
                "order_id": "WO-MVP-002",
                "product_code": "PRD-MVP-002",
                "product_name": "Test Urunu",
                "revision_code": "R2",
                "order_status": self.remote_status,
                "queue_status": queue_status,
                "queue_rank": 1,
                "planned_quantity": 2,
                "uom_code": "ea",
                "operation": {
                    "operation_no": 10,
                    "operation_code": "OP-ASM",
                    "operation_name": "Montaj",
                    "station_code": "ASSEMBLY_01",
                    "status": self.remote_status,
                    "planned_quantity": 2,
                    "good_quantity": self.completed_good if self.remote_status == "completed" else 0,
                    "scrap_quantity": 0,
                    "uom_code": "ea",
                },
            }]
        return {"station_code": "ASSEMBLY_01", "count": len(rows), "queue": rows}

    async def get_station_queue(self, _station_code: str, *, include_done: bool = False) -> dict:
        if self.unavailable:
            raise MesqlUnavailableError()
        return self._queue(include_done)

    async def start_operation(self, **payload) -> dict:
        if self.unavailable:
            raise MesqlUnavailableError()
        self.start_calls.append(payload)
        self.remote_status = "in_progress"
        if self.start_conflict:
            raise MesqlConflictError("already started", detail={"status": "already_started"})
        return {"status": "started"}

    async def complete_operation(self, **payload) -> dict:
        if self.unavailable:
            raise MesqlUnavailableError()
        self.complete_calls.append(payload)
        self.remote_status = "completed"
        if self.complete_conflict:
            raise MesqlConflictError("already completed", detail={"status": "already_completed"})
        return {"status": "completed", "good_quantity": payload["good_quantity"], "scrap_quantity": payload["scrap_quantity"]}


class _UnknownStartConflictMesql(_Mesql):
    async def start_operation(self, **payload) -> dict:
        self.start_calls.append(payload)
        raise MesqlConflictError("unknown conflict", detail={"status": "conflict"})


class MesqlIntegrationTests(unittest.TestCase):
    def _client(
        self,
        *,
        enabled: bool,
        unavailable: bool = False,
        mesql: _Mesql | None = None,
        transition_success: bool = True,
        transition_outcomes: list[bool] | None = None,
        queue_write_result: MesqlQueueWriteResult | None = None,
    ):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        config = AppConfig(
            mesql_enabled=enabled,
            mesql_queue_refresh_sec=3600,
            db_enabled=enabled,
            db_hook_work_order_transitions=enabled,
        )
        env_patch = patch.dict(os.environ, {
            "MES_WEB_OEE_RUNTIME_STATE_PATH": str(root / "runtime.json"),
            "MES_WEB_EXCEL_WORKBOOK_PATH": str(root / "mes.xlsx"),
            "MES_WEB_FERP_EXPORT_PENDING_DIR": str(root / "ferp"),
        }, clear=False)
        env_patch.start()
        self.addCleanup(env_patch.stop)
        manager = OeeRuntimeStateManager(root / "runtime.json")
        manager.write_state(default_runtime_state())
        manager.import_work_orders(
            [{
                "order_id": "WO-MVP-002",
                "qty": 2,
                "product_code": "PRD-MVP-002",
                "stock_code": "PRD-MVP-002",
                "stock_name": "Test Urunu",
                "unit": "ea",
                "station_code": "ASSEMBLY_01",
                "operation_no": 10,
                "operation_code": "OP-ASM",
            }],
            replace_existing=True,
        )
        store = DashboardStore(config)
        store.refresh_oee_runtime_state(config.module_id, force=True)
        hub = SnapshotHub(store, coalesce_ms=config.ws_coalesce_ms)
        runtime = _Runtime(manager)
        mesql = mesql or _Mesql(unavailable=unavailable)
        transition_results = [
            WorkOrderTransitionWriteResult(True, True, False, "written")
            if success
            else WorkOrderTransitionWriteResult(True, False, False, "error_fail_open", error_type="OperationalError")
            for success in (transition_outcomes or [transition_success])
        ]
        transition_patch = (
            patch.object(app_module, "mirror_work_order_transition_from_state", side_effect=transition_results)
            if transition_outcomes is not None
            else patch.object(app_module, "mirror_work_order_transition_from_state", return_value=transition_results[0])
        )
        patches = [
            patch.object(app_module, "config", config),
            patch.object(app_module, "store", store),
            patch.object(app_module, "hub", hub),
            patch.object(app_module, "runtime_service", runtime),
            patch.object(app_module, "oee_state_manager", manager),
            patch.object(app_module, "MesqlClient", return_value=mesql),
            patch.object(app_module, "check_database_health", return_value={"status": "ok"}),
            patch.object(
                app_module,
                "upsert_mesql_queue",
                return_value=queue_write_result or MesqlQueueWriteResult(True, True, 1, "written"),
            ),
            transition_patch,
        ]
        for active_patch in patches:
            active_patch.start()
            self.addCleanup(active_patch.stop)
        client = TestClient(app_module.create_app())
        self.addCleanup(client.close)
        return client, manager, mesql, config

    def test_disabled_keeps_legacy_start_without_mesql_call(self) -> None:
        client, manager, mesql, config = self._client(enabled=False)

        response = client.post(
            f"/api/modules/{config.module_id}/work-orders/start",
            json={"order_id": "WO-MVP-002", "station_code": "ASSEMBLY_01", "operator_code": "OP-1"},
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(manager.read_state()["workOrders"]["ordersById"]["WO-MVP-002"]["status"], "active")
        self.assertEqual(mesql.start_calls, [])

    def test_enabled_queue_start_and_complete(self) -> None:
        client, manager, mesql, config = self._client(enabled=True)

        start = client.post(
            f"/api/modules/{config.module_id}/work-orders/start",
            json={"order_id": "WO-MVP-002", "operator_code": "OP-1"},
        )
        self.assertEqual(start.status_code, 200, start.text)
        self.assertEqual(len(mesql.start_calls), 1)

        manager.finish_work_order("WO-MVP-002", station_code="ASSEMBLY_01", reason="test")
        self.assertEqual(mesql.complete_calls, [])
        state = manager.read_state()
        order = state["workOrders"]["ordersById"]["WO-MVP-002"]
        order["goodQty"] = 2
        order["scrapQty"] = 0
        manager.write_state(state)

        complete = client.post(
            f"/api/modules/{config.module_id}/work-orders/accept-active",
            json={"order_id": "WO-MVP-002", "operator_code": "OP-1"},
        )
        self.assertEqual(complete.status_code, 200, complete.text)
        self.assertEqual(len(mesql.complete_calls), 1)
        self.assertEqual(manager.read_state()["workOrders"]["ordersById"]["WO-MVP-002"]["status"], "completed")

    def test_unavailable_blocks_start_and_accept_without_state_loss(self) -> None:
        client, manager, mesql, config = self._client(enabled=True, unavailable=True)

        start = client.post(
            f"/api/modules/{config.module_id}/work-orders/start",
            json={"order_id": "WO-MVP-002", "station_code": "ASSEMBLY_01", "operator_code": "OP-1"},
        )
        self.assertEqual(start.status_code, 503, start.text)
        self.assertEqual(manager.read_state()["workOrders"]["ordersById"]["WO-MVP-002"]["status"], "queued")

        manager.start_work_order("WO-MVP-002", station_code="ASSEMBLY_01", operator_code="OP-1")
        manager.finish_work_order("WO-MVP-002", station_code="ASSEMBLY_01", reason="test")
        before = manager.read_state()
        accept = client.post(
            f"/api/modules/{config.module_id}/work-orders/accept-active",
            json={"order_id": "WO-MVP-002", "station_code": "ASSEMBLY_01", "operator_code": "OP-1"},
        )
        after = manager.read_state()

        self.assertEqual(accept.status_code, 503, accept.text)
        self.assertEqual(before["workOrders"]["ordersById"]["WO-MVP-002"]["status"], "pending_approval")
        self.assertEqual(after["workOrders"]["ordersById"]["WO-MVP-002"]["status"], "pending_approval")
        self.assertEqual(mesql.start_calls, [])
        self.assertEqual(mesql.complete_calls, [])

    def test_queue_write_failure_returns_database_error_detail_without_remote_start(self) -> None:
        queue_error = MesqlQueueWriteResult(
            True,
            False,
            0,
            "db_error",
            "UniqueViolation",
            "duplicate key violates uq_mes_station_queue_station_active_rank",
        )
        client, manager, mesql, config = self._client(enabled=True, queue_write_result=queue_error)

        response = client.post(
            f"/api/modules/{config.module_id}/work-orders/start",
            json={"order_id": "WO-MVP-002", "station_code": "ASSEMBLY_01", "operator_code": "OP-1"},
        )

        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()["detail"]["code"], "MES_LOCAL_DB_QUEUE_WRITE_FAILED")
        self.assertEqual(response.json()["detail"]["db_error_type"], "UniqueViolation")
        self.assertIn("uq_mes_station_queue_station_active_rank", response.json()["detail"]["db_error_message"])
        self.assertEqual(manager.read_state()["workOrders"]["ordersById"]["WO-MVP-002"]["status"], "queued")
        self.assertEqual(mesql.start_calls, [])

    def test_already_started_is_verified_before_local_start(self) -> None:
        mesql = _Mesql(start_conflict=True)
        client, manager, mesql, config = self._client(enabled=True, mesql=mesql)

        response = client.post(
            f"/api/modules/{config.module_id}/work-orders/start",
            json={"order_id": "WO-MVP-002", "station_code": "ASSEMBLY_01", "operator_code": "OP-1"},
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(mesql.start_calls), 1)
        self.assertEqual(manager.read_state()["workOrders"]["ordersById"]["WO-MVP-002"]["status"], "active")

    def test_unknown_start_conflict_does_not_mutate_local_state(self) -> None:
        mesql = _UnknownStartConflictMesql()
        client, manager, mesql, config = self._client(enabled=True, mesql=mesql)

        response = client.post(
            f"/api/modules/{config.module_id}/work-orders/start",
            json={"order_id": "WO-MVP-002", "station_code": "ASSEMBLY_01", "operator_code": "OP-1"},
        )

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(len(mesql.start_calls), 1)
        self.assertEqual(manager.read_state()["workOrders"]["ordersById"]["WO-MVP-002"]["status"], "queued")

    def test_already_completed_matching_quantities_reconciles_locally_without_retry(self) -> None:
        mesql = _Mesql(complete_conflict=True, completed_good=2)
        client, manager, mesql, config = self._client(enabled=True, mesql=mesql)
        manager.start_work_order("WO-MVP-002", station_code="ASSEMBLY_01", operator_code="OP-1")
        manager.finish_work_order("WO-MVP-002", station_code="ASSEMBLY_01", reason="test")
        state = manager.read_state()
        state["workOrders"]["ordersById"]["WO-MVP-002"]["goodQty"] = 2
        manager.write_state(state)
        mesql.remote_status = "in_progress"

        response = client.post(
            f"/api/modules/{config.module_id}/work-orders/accept-active",
            json={"order_id": "WO-MVP-002", "station_code": "ASSEMBLY_01", "operator_code": "OP-1"},
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(mesql.complete_calls), 1)
        self.assertEqual(manager.read_state()["workOrders"]["ordersById"]["WO-MVP-002"]["status"], "completed")

    def test_already_completed_quantity_mismatch_keeps_pending(self) -> None:
        mesql = _Mesql(complete_conflict=True, completed_good=1)
        client, manager, _mesql, config = self._client(enabled=True, mesql=mesql)
        manager.start_work_order("WO-MVP-002", station_code="ASSEMBLY_01", operator_code="OP-1")
        manager.finish_work_order("WO-MVP-002", station_code="ASSEMBLY_01", reason="test")
        state = manager.read_state()
        state["workOrders"]["ordersById"]["WO-MVP-002"]["goodQty"] = 2
        manager.write_state(state)
        mesql.remote_status = "in_progress"

        response = client.post(
            f"/api/modules/{config.module_id}/work-orders/accept-active",
            json={"order_id": "WO-MVP-002", "station_code": "ASSEMBLY_01", "operator_code": "OP-1"},
        )

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "MESQL_COMPLETION_QUANTITY_MISMATCH")
        self.assertEqual(manager.read_state()["workOrders"]["ordersById"]["WO-MVP-002"]["status"], "pending_approval")

    def test_remote_success_local_db_failure_marks_reconciliation_without_retry(self) -> None:
        client, manager, mesql, config = self._client(enabled=True, transition_success=False)

        response = client.post(
            f"/api/modules/{config.module_id}/work-orders/start",
            json={"order_id": "WO-MVP-002", "station_code": "ASSEMBLY_01", "operator_code": "OP-1"},
        )
        state = manager.read_state()

        self.assertEqual(response.status_code, 500, response.text)
        self.assertEqual(response.json()["detail"]["code"], "MESQL_RECONCILIATION_REQUIRED")
        self.assertEqual(len(mesql.start_calls), 1)
        self.assertIn("start:WO-MVP-002:10", state["integrations"]["mesql"]["reconciliationRequired"])

    def test_explicit_retry_reconciles_local_db_without_second_remote_post(self) -> None:
        client, manager, mesql, config = self._client(enabled=True, transition_outcomes=[False, True])
        payload = {"order_id": "WO-MVP-002", "station_code": "ASSEMBLY_01", "operator_code": "OP-1"}

        first = client.post(f"/api/modules/{config.module_id}/work-orders/start", json=payload)
        retry = client.post(f"/api/modules/{config.module_id}/work-orders/start", json=payload)
        state = manager.read_state()

        self.assertEqual(first.status_code, 500, first.text)
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertTrue(retry.json()["reconciled"])
        self.assertEqual(len(mesql.start_calls), 1)
        self.assertEqual(state["integrations"]["mesql"]["reconciliationRequired"], {})


if __name__ == "__main__":
    unittest.main()

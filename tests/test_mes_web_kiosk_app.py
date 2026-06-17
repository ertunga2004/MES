from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

try:
    from fastapi.testclient import TestClient
    import mes_web.app as app_module
except ModuleNotFoundError:  # pragma: no cover - environment-specific optional dependency
    TestClient = None
    app_module = None

from mes_web.config import AppConfig
from mes_web.oee_state import OeeRuntimeStateManager, default_runtime_state
from mes_web.runtime import SnapshotHub
from mes_web.store import DashboardStore


class _FakeExcelSink:
    def __init__(self) -> None:
        self.kiosk_events: list[tuple[str, dict[str, object], str]] = []

    def record_work_order_state(self, state, received_at: str) -> None:
        return

    def record_kiosk_event(self, event_type: str, payload: dict[str, object], received_at: str) -> None:
        self.kiosk_events.append((event_type, payload, received_at))

    def record_quality_override(self, item_id: str, classification: str, received_at: str) -> None:
        return

    def record_system_oee_log(self, raw_line: str, received_at: str) -> None:
        return

    def record_local_counts_reset(self, received_at: str) -> None:
        return


class _FakeMqttClient:
    def __init__(self) -> None:
        self.published: list[str] = []

    def publish_command(self, payload: str) -> None:
        self.published.append(payload)


class _FakeRuntimeService:
    def __init__(self, manager: OeeRuntimeStateManager) -> None:
        self.oee_manager = manager
        self.excel_sink = _FakeExcelSink()
        self.mqtt_client = _FakeMqttClient()

    async def start(self) -> None:
        return

    async def stop(self) -> None:
        return


class KioskAppTests(unittest.TestCase):
    def _build_client(self):
        if TestClient is None or app_module is None:
            self.skipTest("fastapi is not installed")
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root_dir = Path(__file__).resolve().parents[1]
        state_path = Path(temp_dir.name) / "oee_runtime_state.json"
        workbook_path = Path(temp_dir.name) / "mes.xlsx"
        template_path = root_dir / "MES_Konveyor_Veritabani_Sablonu.xlsx"
        with patch.dict(
            os.environ,
            {
                "MES_WEB_OEE_RUNTIME_STATE_PATH": str(state_path),
                "MES_WEB_EXCEL_WORKBOOK_PATH": str(workbook_path),
                "MES_WEB_EXCEL_TEMPLATE_PATH": str(template_path),
            },
            clear=False,
        ):
            config = AppConfig.from_env()
        manager = OeeRuntimeStateManager(config.oee_runtime_state_path)
        manager.write_state(default_runtime_state())
        store = DashboardStore(config)
        store.refresh_oee_runtime_state(config.module_id, force=True)
        hub = SnapshotHub(store, coalesce_ms=config.ws_coalesce_ms)
        runtime_service = _FakeRuntimeService(manager)
        patches = [
            patch.object(app_module, "config", config),
            patch.object(app_module, "store", store),
            patch.object(app_module, "hub", hub),
            patch.object(app_module, "runtime_service", runtime_service),
            patch.object(app_module, "oee_state_manager", manager),
        ]
        for active_patch in patches:
            active_patch.start()
            self.addCleanup(active_patch.stop)
        app = app_module.create_app()
        client = TestClient(app)
        self.addCleanup(client.close)
        return client, config, manager, store, runtime_service

    def test_kiosk_bootstrap_returns_idle_big_action_and_operator_list(self) -> None:
        client, config, _manager, _store, _runtime_service = self._build_client()

        response = client.get(f"/api/modules/{config.module_id}/kiosk/bootstrap", params={"device_id": "kiosk-1"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["operational_state"], "idle_ready")
        self.assertEqual(payload["big_action"]["label"], "Vardiya Baslat")
        self.assertTrue(payload["operators"])
        robot_fault = next(
            row for row in payload["fault_options"] if row.get("fault_type_code") == "robot_arm_jam"
        )
        self.assertEqual(robot_fault["fault_reason_tr"], "Robot Kol Sıkışması")

    def test_register_then_shift_start_enters_opening_checklist(self) -> None:
        client, config, manager, store, _runtime_service = self._build_client()

        register_response = client.post(
            f"/api/modules/{config.module_id}/kiosk/register",
            json={"device_id": "kiosk-1", "operator_id": "1", "device_name": "Tablet 1"},
        )
        self.assertEqual(register_response.status_code, 200)

        response = client.post(
            f"/api/modules/{config.module_id}/kiosk/shift/start",
            json={"device_id": "kiosk-1", "operator_id": "1", "device_name": "Tablet 1"},
        )

        self.assertEqual(response.status_code, 200)
        store.refresh_oee_runtime_state(config.module_id, force=True)
        state = manager.read_state()
        self.assertEqual(state["operationalState"], "opening_checklist")
        self.assertEqual(state["deviceRegistry"]["kiosk-1"]["lastOperatorId"], "1")

        bootstrap = client.get(f"/api/modules/{config.module_id}/kiosk/bootstrap", params={"device_id": "kiosk-1"}).json()
        self.assertEqual(bootstrap["big_action"]["label"], "Acilis Bakimini Tamamla")
        self.assertEqual(bootstrap["device"]["last_operator_id"], "1")

    def test_fault_start_publishes_stop_and_opens_manual_fault(self) -> None:
        client, config, manager, store, runtime_service = self._build_client()
        manager.apply_control("shift_start")
        store.refresh_oee_runtime_state(config.module_id, force=True)

        response = client.post(
            f"/api/modules/{config.module_id}/kiosk/fault/start",
            json={
                "device_id": "kiosk-1",
                "operator_id": "1",
                "reason_code": "robot_arm_jam",
                "reason_text": "Robot Kol Sikisti",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(runtime_service.mqtt_client.published, ["stop"])
        bootstrap = client.get(f"/api/modules/{config.module_id}/kiosk/bootstrap", params={"device_id": "kiosk-1"}).json()
        self.assertEqual(bootstrap["operational_state"], "manual_fault_active")
        self.assertEqual(bootstrap["active_fault"]["reason"], "Robot Kol Sikisti")

    def test_fault_start_auto_opens_technician_request(self) -> None:
        client, config, manager, store, runtime_service = self._build_client()
        manager.apply_control("shift_start")
        store.refresh_oee_runtime_state(config.module_id, force=True)

        response = client.post(
            f"/api/modules/{config.module_id}/kiosk/fault/start",
            json={
                "device_id": "kiosk-1",
                "operator_id": "1",
                "reason_code": "robot_arm_jam",
                "reason_text": "Robot Kol Sikisti",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(runtime_service.mqtt_client.published, ["stop"])
        request = response.json()["request"]
        self.assertEqual(request["status"], "open")
        self.assertEqual(request["reason"], "Robot Kol Sikisti")
        technician = client.get(
            f"/api/modules/{config.module_id}/technician/bootstrap",
            params={"device_id": "tech-1", "technician_name": "Teknik-1"},
        ).json()
        self.assertEqual(technician["summary"]["open_count"], 1)
        self.assertEqual(technician["active_requests"][0]["request_id"], request["requestId"])
        self.assertEqual(technician["active_requests"][0]["operator_id"], "1")
        self.assertEqual(technician["active_requests"][0]["reason"], "Robot Kol Sikisti")
        event_types = [row[0] for row in runtime_service.excel_sink.kiosk_events]
        self.assertIn("help_requested", event_types)

    def test_technician_ack_and_resolve_closes_fault_and_updates_history(self) -> None:
        client, config, manager, store, runtime_service = self._build_client()
        manager.apply_control("shift_start")
        store.refresh_oee_runtime_state(config.module_id, force=True)
        fault_response = client.post(
            f"/api/modules/{config.module_id}/kiosk/fault/start",
            json={
                "device_id": "kiosk-1",
                "operator_id": "1",
                "reason_code": "robot_arm_jam",
                "reason_text": "Robot Kol Sikisti",
            },
        )
        request_id = fault_response.json()["request"]["requestId"]

        acknowledged = client.post(
            f"/api/modules/{config.module_id}/technician/requests/{request_id}/acknowledge",
            json={"device_id": "tech-1", "technician_name": "Teknik-1"},
        )
        resolved = client.post(
            f"/api/modules/{config.module_id}/technician/requests/{request_id}/resolve",
            json={"device_id": "tech-1", "technician_name": "Teknik-1"},
        )

        self.assertEqual(acknowledged.status_code, 200)
        self.assertEqual(resolved.status_code, 200)
        self.assertTrue(resolved.json()["fault_closed"])
        state = manager.read_state()
        self.assertIsNone(state["activeFault"])
        self.assertEqual(state["operationalState"], "shift_active_running")
        technician = client.get(
            f"/api/modules/{config.module_id}/technician/bootstrap",
            params={"device_id": "tech-1", "technician_name": "Teknik-1"},
        ).json()
        self.assertEqual(technician["summary"]["open_count"], 0)
        self.assertEqual(technician["summary"]["resolved_today_count"], 1)
        self.assertEqual(technician["resolved_today"][0]["request_id"], request_id)
        self.assertEqual(technician["recent_requests"][0]["status"], "resolved")
        event_types = [row[0] for row in runtime_service.excel_sink.kiosk_events]
        self.assertIn("help_acknowledged", event_types)
        self.assertIn("help_resolved", event_types)
        self.assertIn("kiosk_fault_cleared", event_types)

    def test_kiosk_can_publish_system_start_command(self) -> None:
        client, config, _manager, _store, runtime_service = self._build_client()

        response = client.post(
            f"/api/modules/{config.module_id}/kiosk/system/start",
            json={"device_id": "kiosk-1", "operator_id": "1"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(runtime_service.mqtt_client.published, ["start"])

    def test_non_top_kiosk_work_order_requires_reason(self) -> None:
        client, config, manager, store, _runtime_service = self._build_client()
        manager.apply_control("shift_start")
        manager.import_work_orders(
            [
                {"order_id": "WO-001", "stock_code": "BOX-RED", "stock_name": "Kirmizi Kutu", "qty": 1, "color": "red"},
                {"order_id": "WO-002", "stock_code": "BOX-BLUE", "stock_name": "Mavi Kutu", "qty": 1, "color": "blue"},
            ]
        )
        store.refresh_oee_runtime_state(config.module_id, force=True)

        blocked = client.post(
            f"/api/modules/{config.module_id}/kiosk/work-orders/start",
            json={"device_id": "kiosk-1", "operator_id": "1", "order_id": "WO-002"},
        )

        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.json()["detail"]["code"], "KIOSK_QUEUE_REASON_REQUIRED")
        self.assertEqual(blocked.json()["detail"]["priority_order_id"], "WO-001")

        accepted = client.post(
            f"/api/modules/{config.module_id}/kiosk/work-orders/start",
            json={
                "device_id": "kiosk-1",
                "operator_id": "1",
                "order_id": "WO-002",
                "transition_reason": "Kirmizi kutu stokta hazir degil",
            },
        )

        self.assertEqual(accepted.status_code, 200)
        state = manager.read_state()
        self.assertEqual(state["workOrders"]["activeOrderId"], "WO-002")
        self.assertEqual(state["workOrders"]["ordersById"]["WO-002"]["transitionReason"], "Kirmizi kutu stokta hazir degil")

    def test_kiosk_work_order_start_syncs_started_transition_and_active_snapshots(self) -> None:
        client, config, manager, store, _runtime_service = self._build_client()
        manager.apply_control("shift_start")
        manager.import_work_orders(
            [
                {"order_id": "WO-001", "stock_code": "BOX-RED", "stock_name": "Kirmizi Kutu", "qty": 1, "color": "red"},
            ]
        )
        store.refresh_oee_runtime_state(config.module_id, force=True)
        transition_calls: list[dict[str, object]] = []

        def capture_transition(_config, state, *, event_type: str = "runtime_sync", actor_id: str = "", replace_current: bool = False):
            work_orders = state.get("workOrders") if isinstance(state.get("workOrders"), dict) else {}
            active_order_id = str(work_orders.get("activeOrderId") or "")
            orders_by_id = work_orders.get("ordersById") if isinstance(work_orders.get("ordersById"), dict) else {}
            active_order = orders_by_id.get(active_order_id) if isinstance(orders_by_id.get(active_order_id), dict) else {}
            transition_calls.append(
                {
                    "event_type": event_type,
                    "actor_id": actor_id,
                    "active_order_id": active_order_id,
                    "active_status": str(active_order.get("status") or ""),
                    "replace_current": replace_current,
                }
            )
            return None

        with patch.object(app_module, "mirror_work_order_transition_from_state", side_effect=capture_transition):
            response = client.post(
                f"/api/modules/{config.module_id}/kiosk/work-orders/start",
                json={"device_id": "kiosk-1", "operator_id": "1", "order_id": "WO-001"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(transition_calls)
        self.assertEqual(transition_calls[-1]["event_type"], "started")
        self.assertEqual(transition_calls[-1]["actor_id"], "OP-001")
        self.assertEqual(transition_calls[-1]["active_order_id"], "WO-001")
        self.assertEqual(transition_calls[-1]["active_status"], "active")

        dashboard = client.get(f"/api/modules/{config.module_id}/dashboard").json()
        kiosk = client.get(f"/api/modules/{config.module_id}/kiosk/bootstrap", params={"device_id": "kiosk-1"}).json()
        self.assertEqual(dashboard["work_orders"]["active_order"]["order_id"], "WO-001")
        self.assertEqual(kiosk["work_orders"]["active_order"]["order_id"], "WO-001")

    def test_dashboard_station_work_orders_split_active_pending_and_queue(self) -> None:
        client, config, manager, store, _runtime_service = self._build_client()
        manager.import_work_orders(
            [
                {"order_id": "WO-ASM-ACT", "stock_code": "BOX-RED", "stock_name": "Kirmizi Kutu", "qty": 1, "stationCode": "ASSEMBLY_01"},
                {"order_id": "WO-ASM-QUEUE", "stock_code": "BOX-BLUE", "stock_name": "Mavi Kutu", "qty": 3, "stationCode": "ASSEMBLY_01"},
                {"order_id": "WO-PKT-ACT", "stock_code": "PKG_BLUE_3", "stock_name": "Mavi Uclu Paket", "qty": 1, "stationCode": "PACKAGING_01"},
                {"order_id": "WO-PKT-QUEUE", "stock_code": "PKG_RED_YELLOW", "stock_name": "Kirmizi Sari Paket", "qty": 1, "stationCode": "PACKAGING_01"},
            ]
        )
        state = manager.read_state()
        orders = state["workOrders"]["ordersById"]
        orders["WO-ASM-ACT"]["status"] = "active"
        orders["WO-ASM-ACT"]["startedAt"] = "2026-04-27T09:00:00+00:00"
        orders["WO-PKT-ACT"]["status"] = "active"
        orders["WO-PKT-ACT"]["startedAt"] = "2026-04-27T09:01:00+00:00"
        orders["WO-PKT-QUEUE"]["status"] = "pending_approval"
        orders["WO-PKT-QUEUE"]["startedAt"] = "2026-04-27T09:02:00+00:00"
        orders["WO-PKT-QUEUE"]["completedQty"] = 1
        orders["WO-PKT-QUEUE"]["productionQty"] = 1
        orders["WO-PKT-QUEUE"]["goodQty"] = 1
        orders["WO-PKT-QUEUE"]["remainingQty"] = 0
        orders["WO-PKT-QUEUE"]["autoCompletedAt"] = "2026-04-27T09:03:00+00:00"
        orders["WO-PKT-QUEUE"]["lastAllocationAt"] = "2026-04-27T09:03:00+00:00"
        for requirement in orders["WO-PKT-QUEUE"].get("requirements") or []:
            requirement["completedQty"] = requirement.get("quantity", 1)
            requirement["productionQty"] = requirement.get("quantity", 1)
            requirement["remainingQty"] = 0
        state["workOrders"]["activeOrderId"] = "WO-ASM-ACT"
        manager.write_state(state)
        store.refresh_oee_runtime_state(config.module_id, force=True)
        availability = {
            "bom_configured": True,
            "can_start": True,
            "package_stock_code": "PKG_BLUE_3",
            "components": [
                {
                    "component_stock_code": "BLUE_BOX",
                    "required_qty": 3,
                    "available_qty": 2,
                    "missing_qty": 1,
                }
            ],
        }

        with patch.object(app_module, "package_component_availability", return_value=availability):
            dashboard = client.get(f"/api/modules/{config.module_id}/dashboard").json()

        board = dashboard["station_work_orders"]
        self.assertEqual(board["ASSEMBLY_01"]["active_order"]["order_id"], "WO-ASM-ACT")
        self.assertEqual(board["ASSEMBLY_01"]["queue_order_ids"], ["WO-ASM-QUEUE"])
        self.assertEqual(board["PACKAGING_01"]["active_order"]["order_id"], "WO-PKT-ACT")
        self.assertEqual(board["PACKAGING_01"]["pending_order"]["order_id"], "WO-PKT-QUEUE")
        self.assertEqual(board["PACKAGING_01"]["queue_order_ids"], [])
        self.assertEqual(board["PACKAGING_01"]["package_wip_summary"][0]["component_stock_code"], "BLUE_BOX")
        self.assertEqual(board["PACKAGING_01"]["package_wip_summary"][0]["missing_qty"], 1)

    def test_dashboard_station_reorder_only_changes_requested_station_queue(self) -> None:
        client, config, manager, store, _runtime_service = self._build_client()
        manager.import_work_orders(
            [
                {"order_id": "WO-ASM-1", "stock_code": "BOX-RED", "stock_name": "Kirmizi Kutu", "qty": 1, "stationCode": "ASSEMBLY_01"},
                {"order_id": "WO-PKG-1", "stock_code": "PKG_BLUE_3", "stock_name": "Mavi Uclu Paket", "qty": 1, "stationCode": "PACKAGING_01"},
                {"order_id": "WO-ASM-2", "stock_code": "BOX-YELLOW", "stock_name": "Sari Kutu", "qty": 1, "stationCode": "ASSEMBLY_01"},
                {"order_id": "WO-PKG-2", "stock_code": "PKG_RED_YELLOW", "stock_name": "Kirmizi Sari Paket", "qty": 1, "stationCode": "PACKAGING_01"},
            ]
        )
        store.refresh_oee_runtime_state(config.module_id, force=True)

        response = client.post(
            f"/api/modules/{config.module_id}/work-orders/reorder",
            json={
                "station_code": "ASSEMBLY_01",
                "ordered_order_ids": ["WO-ASM-2", "WO-ASM-1"],
                "reason": "test_station_reorder",
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["station_code"], "ASSEMBLY_01")
        state = manager.read_state()
        self.assertEqual(
            state["workOrders"]["orderSequence"],
            ["WO-ASM-2", "WO-PKG-1", "WO-ASM-1", "WO-PKG-2"],
        )

        wrong_station = client.post(
            f"/api/modules/{config.module_id}/work-orders/reorder",
            json={
                "station_code": "ASSEMBLY_01",
                "ordered_order_ids": ["WO-PKG-1", "WO-ASM-1"],
                "reason": "test_wrong_station",
            },
        )
        self.assertEqual(wrong_station.status_code, 400)
        self.assertEqual(wrong_station.json()["detail"], "WORK_ORDER_STATION_MISMATCH")

        state = manager.read_state()
        state["workOrders"]["ordersById"]["WO-ASM-2"]["status"] = "active"
        state["workOrders"]["ordersById"]["WO-ASM-2"]["startedAt"] = "2026-04-27T09:00:00+00:00"
        manager.write_state(state)
        active_reorder = client.post(
            f"/api/modules/{config.module_id}/work-orders/reorder",
            json={
                "station_code": "ASSEMBLY_01",
                "ordered_order_ids": ["WO-ASM-2", "WO-ASM-1"],
                "reason": "test_active_reorder",
            },
        )
        self.assertEqual(active_reorder.status_code, 400)
        self.assertEqual(active_reorder.json()["detail"], "INVALID_WORK_ORDER_REORDER")

    def test_dashboard_reorder_requires_reason(self) -> None:
        client, config, manager, store, _runtime_service = self._build_client()
        manager.import_work_orders(
            [
                {"order_id": "WO-ASM-1", "stock_code": "BOX-RED", "stock_name": "Kirmizi Kutu", "qty": 1, "stationCode": "ASSEMBLY_01"},
                {"order_id": "WO-ASM-2", "stock_code": "BOX-BLUE", "stock_name": "Mavi Kutu", "qty": 1, "stationCode": "ASSEMBLY_01"},
            ]
        )
        store.refresh_oee_runtime_state(config.module_id, force=True)

        response = client.post(
            f"/api/modules/{config.module_id}/work-orders/reorder",
            json={"station_code": "ASSEMBLY_01", "ordered_order_ids": ["WO-ASM-2", "WO-ASM-1"]},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "WORK_ORDER_REORDER_REASON_REQUIRED")

    def test_successful_reorder_writes_reordered_event(self) -> None:
        client, config, manager, store, _runtime_service = self._build_client()
        manager.import_work_orders(
            [
                {"order_id": "WO-ASM-1", "stock_code": "BOX-RED", "stock_name": "Kirmizi Kutu", "qty": 1, "stationCode": "ASSEMBLY_01"},
                {"order_id": "WO-ASM-2", "stock_code": "BOX-BLUE", "stock_name": "Mavi Kutu", "qty": 1, "stationCode": "ASSEMBLY_01"},
            ]
        )
        store.refresh_oee_runtime_state(config.module_id, force=True)
        calls: list[dict[str, object]] = []

        def capture_transition(_config, state, *, event_type: str = "runtime_sync", actor_id: str = "", replace_current: bool = False):
            calls.append({"event_type": event_type, "replace_current": replace_current})
            return None

        with patch.object(app_module, "mirror_work_order_transition_from_state", side_effect=capture_transition):
            response = client.post(
                f"/api/modules/{config.module_id}/work-orders/reorder",
                json={
                    "station_code": "ASSEMBLY_01",
                    "ordered_order_ids": ["WO-ASM-2", "WO-ASM-1"],
                    "reason": "test_reorder_event",
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(calls)
        self.assertEqual(calls[-1]["event_type"], "reordered")

    def test_cancel_requires_reason_and_rejects_wrong_station(self) -> None:
        client, config, manager, store, _runtime_service = self._build_client()
        manager.import_work_orders(
            [
                {"order_id": "WO-ASM-1", "stock_code": "BOX-RED", "stock_name": "Kirmizi Kutu", "qty": 1, "stationCode": "ASSEMBLY_01"},
            ]
        )
        store.refresh_oee_runtime_state(config.module_id, force=True)

        missing_reason = client.post(
            f"/api/modules/{config.module_id}/work-orders/cancel",
            json={"station_code": "ASSEMBLY_01", "order_id": "WO-ASM-1"},
        )
        wrong_station = client.post(
            f"/api/modules/{config.module_id}/work-orders/cancel",
            json={"station_code": "PACKAGING_01", "order_id": "WO-ASM-1", "reason": "operator_cancel"},
        )

        self.assertEqual(missing_reason.status_code, 400)
        self.assertEqual(missing_reason.json()["detail"], "WORK_ORDER_CANCEL_REASON_REQUIRED")
        self.assertEqual(wrong_station.status_code, 400)
        self.assertEqual(wrong_station.json()["detail"], "WORK_ORDER_STATION_MISMATCH")

    def test_successful_cancel_writes_cancelled_event(self) -> None:
        client, config, manager, store, _runtime_service = self._build_client()
        manager.import_work_orders(
            [
                {"order_id": "WO-ASM-1", "stock_code": "BOX-RED", "stock_name": "Kirmizi Kutu", "qty": 1, "stationCode": "ASSEMBLY_01"},
            ]
        )
        store.refresh_oee_runtime_state(config.module_id, force=True)
        calls: list[dict[str, object]] = []

        def capture_transition(_config, state, *, event_type: str = "runtime_sync", actor_id: str = "", replace_current: bool = False):
            calls.append({"event_type": event_type, "actor_id": actor_id})
            return None

        with patch.object(app_module, "mirror_work_order_transition_from_state", side_effect=capture_transition):
            response = client.post(
                f"/api/modules/{config.module_id}/work-orders/cancel",
                json={
                    "station_code": "ASSEMBLY_01",
                    "order_id": "WO-ASM-1",
                    "operator_id": "OP-001",
                    "reason": "operator_cancel",
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(calls)
        self.assertEqual(calls[-1]["event_type"], "cancelled")
        self.assertEqual(calls[-1]["actor_id"], "OP-001")

    def test_active_assembly_cancel_does_not_clear_packaging_active(self) -> None:
        client, config, manager, store, _runtime_service = self._build_client()
        manager.import_work_orders(
            [
                {"order_id": "WO-ASM-ACT", "stock_code": "BOX-RED", "stock_name": "Kirmizi Kutu", "qty": 1, "stationCode": "ASSEMBLY_01"},
                {"order_id": "WO-PKG-ACT", "stock_code": "PKG_BLUE_3", "stock_name": "Mavi Uclu Paket", "qty": 1, "stationCode": "PACKAGING_01"},
            ]
        )
        manager.start_work_order("WO-ASM-ACT", station_code="ASSEMBLY_01")
        manager.start_work_order("WO-PKG-ACT", station_code="PACKAGING_01")
        store.refresh_oee_runtime_state(config.module_id, force=True)

        response = client.post(
            f"/api/modules/{config.module_id}/work-orders/cancel",
            json={"station_code": "ASSEMBLY_01", "order_id": "WO-ASM-ACT", "reason": "operator_cancel"},
        )

        self.assertEqual(response.status_code, 200, response.text)
        state = manager.read_state()
        self.assertEqual(state["workOrders"]["ordersById"]["WO-ASM-ACT"]["status"], "cancelled")
        self.assertEqual(state["workOrders"]["ordersById"]["WO-PKG-ACT"]["status"], "active")
        self.assertEqual(state["workOrders"]["activeOrderByStation"].get("PACKAGING_01"), "WO-PKG-ACT")
        self.assertNotIn("ASSEMBLY_01", state["workOrders"]["activeOrderByStation"])

    def test_active_package_cancel_releases_runtime_and_db_wip(self) -> None:
        client, config, manager, store, _runtime_service = self._build_client()
        manager.import_work_orders(
            [
                {"order_id": "WO-PKG-ACT", "stock_code": "PKG_BLUE_3", "stock_name": "Mavi Uclu Paket", "qty": 1, "stationCode": "PACKAGING_01"},
            ]
        )
        state = manager.read_state()
        order = state["workOrders"]["ordersById"]["WO-PKG-ACT"]
        order["status"] = "active"
        order["startedAt"] = "2026-04-27T09:00:00+00:00"
        session_id = "SESSION-1"
        state["workOrders"]["activeOrderByStation"] = {"PACKAGING_01": "WO-PKG-ACT"}
        state["workOrders"]["packagingSessions"] = {
            session_id: {
                "session_id": session_id,
                "package_order_id": "WO-PKG-ACT",
                "buffer_item_id": "BUF-1",
                "status": "reserved",
            }
        }
        state["workOrders"]["packagingBuffer"] = {
            "itemsById": {
                "BUF-1": {
                    "item_id": "BUF-1",
                    "item_key": "ITEM-1",
                    "status": "reserved",
                    "reserved_by_order_id": "WO-PKG-ACT",
                    "reserved_by_session_id": session_id,
                }
            },
            "availableItemIds": [],
        }
        state["itemsById"] = {
            "ITEM-1": {
                "item_id": "BUF-1",
                "completed_at": "2026-04-27T08:00:00+00:00",
                "classification": "GOOD",
                "color": "blue",
                "final_color": "blue",
                "product_code": "BLUE_BOX",
                "stock_code": "BLUE_BOX",
                "packaging_status": "reserved",
                "packaging_order_id": "WO-PKG-ACT",
                "packaging_session_id": session_id,
            }
        }
        manager.write_state(state)
        store.refresh_oee_runtime_state(config.module_id, force=True)

        with patch.object(app_module, "release_reserved_package_components", return_value=[{"wip_item_pk": 1}]) as release_mock:
            response = client.post(
                f"/api/modules/{config.module_id}/work-orders/cancel",
                json={"station_code": "PACKAGING_01", "order_id": "WO-PKG-ACT", "reason": "operator_cancel"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        release_mock.assert_called_once()
        state = manager.read_state()
        self.assertEqual(state["workOrders"]["packagingSessions"][session_id]["status"], "cancelled")
        buffer_items = state["workOrders"]["packagingBuffer"]["itemsById"]
        self.assertTrue(buffer_items)
        buffer_row = next(iter(buffer_items.values()))
        self.assertEqual(buffer_row["status"], "available")
        self.assertTrue(state["workOrders"]["packagingBuffer"]["availableItemIds"])
        self.assertEqual(response.json()["released_component_count"], 1)

    def test_pending_package_cancel_is_not_supported(self) -> None:
        client, config, manager, store, _runtime_service = self._build_client()
        manager.import_work_orders(
            [
                {"order_id": "WO-PKG-PENDING", "stock_code": "PKG_BLUE_3", "stock_name": "Mavi Uclu Paket", "qty": 1, "stationCode": "PACKAGING_01"},
            ]
        )
        state = manager.read_state()
        order = state["workOrders"]["ordersById"]["WO-PKG-PENDING"]
        order["status"] = "pending_approval"
        order["startedAt"] = "2026-04-27T09:00:00+00:00"
        order["completedQty"] = 1
        order["productionQty"] = 1
        order["remainingQty"] = 0
        order["autoCompletedAt"] = "2026-04-27T09:05:00+00:00"
        for requirement in order.get("requirements") or []:
            requirement["completedQty"] = requirement.get("quantity", 1)
            requirement["productionQty"] = requirement.get("quantity", 1)
            requirement["remainingQty"] = 0
        state["workOrders"]["activeOrderByStation"] = {"PACKAGING_01": "WO-PKG-PENDING"}
        manager.write_state(state)
        store.refresh_oee_runtime_state(config.module_id, force=True)

        response = client.post(
            f"/api/modules/{config.module_id}/work-orders/cancel",
            json={"station_code": "PACKAGING_01", "order_id": "WO-PKG-PENDING", "reason": "operator_cancel"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "PACKAGE_PENDING_ROLLBACK_NOT_SUPPORTED")

    def test_work_order_reset_triggers_demo_wip_cleanup_by_default(self) -> None:
        client, config, manager, store, _runtime_service = self._build_client()
        manager.import_work_orders(
            [
                {"order_id": "WO-ASM-1", "stock_code": "BOX-RED", "stock_name": "Kirmizi Kutu", "qty": 1, "stationCode": "ASSEMBLY_01"},
            ]
        )
        state = manager.read_state()
        state["workOrders"]["packagingBuffer"] = {
            "itemsById": {
                "BUF-RED-1": {
                    "item_id": "BUF-RED-1",
                    "status": "available",
                    "classification": "GOOD",
                    "color": "red",
                    "product_code": "RED_BOX",
                }
            },
            "availableItemIds": ["BUF-RED-1"],
        }
        manager.write_state(state)
        store.refresh_oee_runtime_state(config.module_id, force=True)

        with patch.object(app_module, "reset_demo_package_wip", return_value=3) as reset_wip_mock:
            response = client.post(f"/api/modules/{config.module_id}/work-orders/reset", json={})

        self.assertEqual(response.status_code, 200, response.text)
        reset_wip_mock.assert_called_once()
        self.assertEqual(response.json()["wip_reset_count"], 3)
        state = manager.read_state()
        self.assertEqual(state["workOrders"]["packagingBuffer"], {"itemsById": {}, "availableItemIds": []})

    def test_kiosk_accept_active_work_order_syncs_completed_transition(self) -> None:
        client, config, manager, store, _runtime_service = self._build_client()
        order_id = "WO-ACCEPT"
        manager.import_work_orders(
            [
                {
                    "order_id": order_id,
                    "qty": 1,
                    "stock_code": "BOX-RED",
                    "stock_name": "Kirmizi Kutu",
                    "product_color": "red",
                    "unit": "ADET",
                    "cycleTimeSec": 15,
                }
            ],
            now=datetime(2026, 4, 27, 9, 0, tzinfo=timezone.utc),
        )
        manager.start_work_order(order_id, operator_code="OP-001", now=datetime(2026, 4, 27, 9, 1, tzinfo=timezone.utc))
        manager.apply_mega_log(
            "MEGA|AUTO|QUEUE=ENQ|ITEM_ID=ITEM-1|MEASURE_ID=1|COLOR=KIRMIZI|DECISION_SOURCE=CORE_STABLE|TRAVEL_MS=4500|PENDING=1",
            "2026-04-27T09:02:00Z",
        )
        manager.apply_mega_log(
            "MEGA|ROBOT|EVENT=RELEASED|ITEM_ID=ITEM-1|MEASURE_ID=1|TRIGGER=TIMER",
            "2026-04-27T09:02:10Z",
        )
        store.refresh_oee_runtime_state(config.module_id, force=True)
        prepared_state = manager.read_state()
        self.assertEqual(prepared_state["workOrders"]["ordersById"][order_id]["status"], "pending_approval")
        transition_calls: list[dict[str, object]] = []

        def capture_transition(_config, state, *, event_type: str = "runtime_sync", actor_id: str = "", replace_current: bool = False):
            work_orders = state.get("workOrders") if isinstance(state.get("workOrders"), dict) else {}
            order = ((work_orders.get("ordersById") or {}) if isinstance(work_orders.get("ordersById"), dict) else {}).get(order_id) or {}
            transition_calls.append(
                {
                    "event_type": event_type,
                    "actor_id": actor_id,
                    "active_order_id": str(work_orders.get("activeOrderId") or ""),
                    "status": str(order.get("status") or ""),
                    "replace_current": replace_current,
                }
            )
            return None

        with patch.object(app_module, "mirror_work_order_transition_from_state", side_effect=capture_transition):
            response = client.post(f"/api/modules/{config.module_id}/kiosk/work-orders/accept-active")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(transition_calls)
        self.assertEqual(transition_calls[-1]["event_type"], "completed")
        self.assertEqual(transition_calls[-1]["active_order_id"], "")
        self.assertEqual(transition_calls[-1]["status"], "completed")
        self.assertEqual(response.json()["order_id"], order_id)

    def test_kiosk_work_order_reason_required_response_exposes_ms_fields(self) -> None:
        client, config, manager, _store, _runtime_service = self._build_client()
        client.post(
            f"/api/modules/{config.module_id}/kiosk/register",
            json={"device_id": "kiosk-1", "operator_id": "1", "device_name": "Tablet 1"},
        )
        manager.apply_control("shift_start")
        manager.import_work_orders(
            [
                {"order_id": "WO-001", "stock_code": "BOX-RED", "stock_name": "Kirmizi Kutu", "qty": 1, "color": "red"},
            ]
        )
        state = manager.read_state()
        state["workOrders"]["lastCompletedOrderId"] = "WO-000"
        state["workOrders"]["lastCompletedAt"] = "2026-04-02T08:00:00+03:00"
        state["workOrders"]["toleranceMs"] = 5 * 60 * 1000
        state["workOrders"]["toleranceMinutes"] = 5.0
        manager.write_state(state)

        blocked = client.post(
            f"/api/modules/{config.module_id}/kiosk/work-orders/start",
            json={
                "device_id": "kiosk-1",
                "operator_id": "1",
                "order_id": "WO-001",
                "started_at": "2026-04-02T08:10:00+03:00",
            },
        )

        self.assertEqual(blocked.status_code, 409)
        detail = blocked.json()["detail"]
        self.assertEqual(detail["code"], "WORK_ORDER_REASON_REQUIRED")
        self.assertEqual(detail["elapsed_ms"], 10 * 60 * 1000)
        self.assertEqual(detail["tolerance_ms"], 5 * 60 * 1000)

    def test_kiosk_package_work_order_start_does_not_gate_or_reserve_wip(self) -> None:
        client, config, manager, store, _runtime_service = self._build_client()
        manager.apply_control("shift_start")
        manager.import_work_orders(
            [
                {
                    "order_id": "WO-PKT-BLUE-001",
                    "stock_code": "PKG_BLUE_3",
                    "stock_name": "Mavi Uclu Paket",
                    "qty": 1,
                    "stationCode": "PACKAGING_01",
                }
            ]
        )
        store.refresh_oee_runtime_state(config.module_id, force=True)
        availability = {
            "bom_configured": True,
            "can_start": False,
            "package_stock_code": "PKG_BLUE_3",
            "components": [
                {
                    "component_stock_code": "BLUE_BOX",
                    "required_qty": 3,
                    "available_qty": 1,
                    "missing_qty": 2,
                }
            ],
        }

        with patch.object(app_module, "package_component_availability", return_value=availability):
            started = client.post(
                f"/api/modules/{config.module_id}/kiosk/work-orders/start",
                json={
                    "device_id": "kiosk-1",
                    "operator_id": "1",
                    "order_id": "WO-PKT-BLUE-001",
                    "station_code": "PACKAGING_01",
                },
            )

        self.assertEqual(started.status_code, 200, started.text)
        state = manager.read_state()
        order = state["workOrders"]["ordersById"]["WO-PKT-BLUE-001"]
        self.assertEqual(order["status"], "active")
        self.assertEqual(state["workOrders"]["packagingSessions"], {})

    def test_kiosk_package_start_blocks_when_bom_components_missing(self) -> None:
        client, config, manager, store, _runtime_service = self._build_client()
        manager.import_work_orders(
            [
                {
                    "order_id": "WO-PKT-BLUE-001",
                    "stock_code": "PKG_BLUE_3",
                    "stock_name": "Mavi Uclu Paket",
                    "qty": 1,
                    "stationCode": "PACKAGING_01",
                }
            ]
        )
        manager.start_work_order("WO-PKT-BLUE-001", station_code="PACKAGING_01")
        store.refresh_oee_runtime_state(config.module_id, force=True)
        availability = {
            "bom_configured": True,
            "can_start": False,
            "package_stock_code": "PKG_BLUE_3",
            "components": [
                {
                    "component_stock_code": "BLUE_BOX",
                    "required_qty": 3,
                    "available_qty": 0,
                    "missing_qty": 3,
                }
            ],
        }

        with patch.object(app_module, "package_component_availability", return_value=availability):
            blocked = client.post(
                f"/api/modules/{config.module_id}/kiosk/package/start",
                json={"device_id": "kiosk-1", "operator_id": "1", "package_order_id": "WO-PKT-BLUE-001"},
            )

        self.assertEqual(blocked.status_code, 409)
        detail = blocked.json()["detail"]
        self.assertEqual(detail["code"], "PACKAGE_COMPONENTS_NOT_AVAILABLE")
        self.assertEqual(detail["package_stock_code"], "PKG_BLUE_3")

    def test_kiosk_packaging_snapshot_exposes_package_bom_availability(self) -> None:
        client, config, manager, store, _runtime_service = self._build_client()
        manager.import_work_orders(
            [
                {
                    "order_id": "WO-PKT-BLUE-001",
                    "stock_code": "PKG_BLUE_3",
                    "stock_name": "Mavi Uclu Paket",
                    "qty": 1,
                    "stationCode": "PACKAGING_01",
                }
            ]
        )
        store.refresh_oee_runtime_state(config.module_id, force=True)
        availability = {
            "bom_configured": True,
            "can_start": True,
            "package_stock_code": "PKG_BLUE_3",
            "components": [
                {
                    "component_stock_code": "BLUE_BOX",
                    "required_qty": 3,
                    "available_qty": 3,
                    "missing_qty": 0,
                }
            ],
        }

        with patch.object(app_module, "package_component_availability", return_value=availability):
            snapshot = client.get(
                f"/api/modules/{config.module_id}/kiosk/bootstrap",
                params={"device_id": "kiosk-1", "station_code": "PACKAGING_01"},
            ).json()

        package_orders = snapshot["packaging"]["package_orders"]
        self.assertEqual(len(package_orders), 1)
        self.assertEqual(package_orders[0]["package_bom"]["package_stock_code"], "PKG_BLUE_3")
        self.assertEqual(package_orders[0]["package_bom"]["components"][0]["available_qty"], 3)

    def test_kiosk_package_start_reserves_phase2_components_when_available(self) -> None:
        client, config, manager, store, _runtime_service = self._build_client()
        manager.import_work_orders(
            [
                {
                    "order_id": "WO-PKT-BLUE-001",
                    "stock_code": "PKG_BLUE_3",
                    "stock_name": "Mavi Uclu Paket",
                    "qty": 1,
                    "stationCode": "PACKAGING_01",
                }
            ]
        )
        manager.start_work_order("WO-PKT-BLUE-001", station_code="PACKAGING_01")
        state = manager.read_state()
        state["workOrders"]["packagingBuffer"] = {
            "itemsById": {
                "BUF-1": {
                    "item_id": "BUF-1",
                    "status": "available",
                    "classification": "GOOD",
                    "color": "blue",
                    "product_code": "BLUE_BOX",
                }
            },
            "availableItemIds": ["BUF-1"],
        }
        manager.write_state(state)
        store.refresh_oee_runtime_state(config.module_id, force=True)
        availability = {
            "bom_configured": True,
            "can_start": True,
            "package_stock_code": "PKG_BLUE_3",
            "components": [
                {
                    "component_stock_code": "BLUE_BOX",
                    "required_qty": 3,
                    "available_qty": 3,
                    "missing_qty": 0,
                }
            ],
        }

        with patch.object(app_module, "package_component_availability", return_value=availability), patch.object(
            app_module,
            "reserve_package_components",
            return_value=[{"wip_item_pk": 1}, {"wip_item_pk": 2}, {"wip_item_pk": 3}],
        ) as reserve_mock:
            response = client.post(
                f"/api/modules/{config.module_id}/kiosk/package/start",
                json={"device_id": "kiosk-1", "operator_id": "1", "package_order_id": "WO-PKT-BLUE-001"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["reserved_component_count"], 3)
        reserve_mock.assert_called_once()
        state = manager.read_state()
        sessions = state["workOrders"]["packagingSessions"]
        self.assertEqual(len(sessions), 1)
        session = next(iter(sessions.values()))
        self.assertEqual(session["status"], "in_progress")
        self.assertEqual(state["workOrders"]["ordersById"]["WO-PKT-BLUE-001"]["status"], "active")

    def test_package_lifecycle_requires_start_finish_accept_sequence(self) -> None:
        client, config, manager, store, _runtime_service = self._build_client()
        manager.apply_control("shift_start")
        manager.import_work_orders(
            [
                {
                    "order_id": "WO-PKT-BLUE-001",
                    "stock_code": "PKG_BLUE_3",
                    "stock_name": "Mavi Uclu Paket",
                    "qty": 1,
                    "stationCode": "PACKAGING_01",
                }
            ]
        )
        state = manager.read_state()
        state["workOrders"]["packagingBuffer"] = {
            "itemsById": {
                "BUF-1": {
                    "item_id": "BUF-1",
                    "item_key": "ITEM-1",
                    "status": "available",
                    "classification": "GOOD",
                    "color": "blue",
                    "product_code": "BLUE_BOX",
                    "upstream_order_id": "TEST-FERP-SCRAP",
                    "upstream_external_ref": "TEST-FERP-SCRAP_BUF-1",
                }
            },
            "availableItemIds": ["BUF-1"],
        }
        state["itemsById"] = {
            "ITEM-1": {
                "item_id": "BUF-1",
                "completed_at": "2026-04-27T08:00:00+00:00",
                "classification": "GOOD",
                "color": "blue",
                "final_color": "blue",
                "product_code": "BLUE_BOX",
                "stock_code": "BLUE_BOX",
                "work_order_id": "TEST-FERP-SCRAP",
            }
        }
        manager.write_state(state)
        store.refresh_oee_runtime_state(config.module_id, force=True)
        availability = {
            "bom_configured": True,
            "can_start": True,
            "package_stock_code": "PKG_BLUE_3",
            "components": [
                {
                    "component_stock_code": "BLUE_BOX",
                    "required_qty": 3,
                    "available_qty": 3,
                    "missing_qty": 0,
                }
            ],
        }

        with patch.object(app_module, "package_component_availability", return_value=availability):
            started = client.post(
                f"/api/modules/{config.module_id}/kiosk/work-orders/start",
                json={
                    "device_id": "kiosk-1",
                    "operator_id": "1",
                    "order_id": "WO-PKT-BLUE-001",
                    "station_code": "PACKAGING_01",
                },
            )
            self.assertEqual(started.status_code, 200, started.text)
            snapshot = client.get(
                f"/api/modules/{config.module_id}/kiosk/bootstrap",
                params={"device_id": "kiosk-1", "station_code": "PACKAGING_01"},
            ).json()

        self.assertEqual(snapshot["big_action"]["action"], "package_start")
        state = manager.read_state()
        self.assertEqual(state["workOrders"]["ordersById"]["WO-PKT-BLUE-001"]["status"], "active")
        self.assertEqual(state["workOrders"]["packagingSessions"], {})

        with patch.object(app_module, "package_component_availability", return_value=availability), patch.object(
            app_module,
            "reserve_package_components",
            return_value=[{"wip_item_pk": 1}, {"wip_item_pk": 2}, {"wip_item_pk": 3}],
        ):
            package_started = client.post(
                f"/api/modules/{config.module_id}/kiosk/package/start",
                json={"device_id": "kiosk-1", "operator_id": "1", "package_order_id": "WO-PKT-BLUE-001"},
            )
            self.assertEqual(package_started.status_code, 200, package_started.text)
            snapshot = client.get(
                f"/api/modules/{config.module_id}/kiosk/bootstrap",
                params={"device_id": "kiosk-1", "station_code": "PACKAGING_01"},
            ).json()

        self.assertEqual(snapshot["big_action"]["action"], "package_finish")
        state = manager.read_state()
        sessions = state["workOrders"]["packagingSessions"]
        session_id = next(iter(sessions))
        self.assertEqual(sessions[session_id]["status"], "in_progress")
        sessions[session_id]["started_at"] = "2026-04-27T09:00:00+00:00"
        manager.write_state(state)

        with patch.object(app_module, "consume_package_components", return_value=[{"wip_item_pk": 1}, {"wip_item_pk": 2}, {"wip_item_pk": 3}]):
            package_finished = client.post(
                f"/api/modules/{config.module_id}/kiosk/package/finish",
                json={"device_id": "kiosk-1", "operator_id": "1", "session_id": session_id},
            )

        self.assertEqual(package_finished.status_code, 200, package_finished.text)
        self.assertGreater(package_finished.json()["duration_seconds"], 0)
        state = manager.read_state()
        order = state["workOrders"]["ordersById"]["WO-PKT-BLUE-001"]
        self.assertEqual(order["status"], "pending_approval")
        self.assertEqual(state["workOrders"]["packagingSessions"][session_id]["status"], "finished")
        self.assertGreater(state["workOrders"]["packagingSessions"][session_id]["duration_seconds"], 0)

        accepted = client.post(
            f"/api/modules/{config.module_id}/kiosk/work-orders/accept-active",
            json={"station_code": "PACKAGING_01", "order_id": "WO-PKT-BLUE-001"},
        )

        self.assertEqual(accepted.status_code, 200, accepted.text)
        state = manager.read_state()
        self.assertEqual(state["workOrders"]["ordersById"]["WO-PKT-BLUE-001"]["status"], "completed")
        self.assertNotIn("PACKAGING_01", state["workOrders"].get("activeOrderByStation") or {})


if __name__ == "__main__":
    unittest.main()

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

    def test_kiosk_package_work_order_start_blocks_when_bom_components_missing(self) -> None:
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
            blocked = client.post(
                f"/api/modules/{config.module_id}/kiosk/work-orders/start",
                json={
                    "device_id": "kiosk-1",
                    "operator_id": "1",
                    "order_id": "WO-PKT-BLUE-001",
                    "station_code": "PACKAGING_01",
                },
            )

        self.assertEqual(blocked.status_code, 409)
        detail = blocked.json()["detail"]
        self.assertEqual(detail["code"], "PACKAGE_COMPONENTS_NOT_AVAILABLE")
        self.assertEqual(detail["components"][0]["component_stock_code"], "BLUE_BOX")
        self.assertEqual(detail["components"][0]["missing_qty"], 2)

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


if __name__ == "__main__":
    unittest.main()

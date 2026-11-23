from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
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
    def _sample_package_work_order(self) -> dict:
        return {
            "workOrderId": "WO-PKT-A-001",
            "productId": "PKT-A",
            "productName": "PKT-A Paket",
            "targetQty": 3,
            "materials": [
                {"itemCode": "KUTU-KRM", "itemName": "Kirmizi Kutu", "itemType": "box", "color": "red", "qtyPerUnit": 1},
                {"itemCode": "KUTU-SRI", "itemName": "Sari Kutu", "itemType": "box", "color": "yellow", "qtyPerUnit": 1},
                {"itemCode": "BON-BYZ", "itemName": "Beyaz Boncuk", "itemType": "bead", "color": "white", "qtyPerUnit": 2},
                {"itemCode": "KAGIT-PKT-01", "itemName": "Kagit Paket", "itemType": "package", "qtyPerUnit": 1},
                {"itemCode": "ETK-PKT-A", "itemName": "Paket Etiketi", "itemType": "label", "qtyPerUnit": 1},
                {"itemCode": "KLVZ-PKT-01", "itemName": "Kullanim Kilavuzu", "itemType": "consumable", "qtyPerUnit": 1},
                {"itemCode": "BANT-PKT-01", "itemName": "Paket Bandi", "itemType": "consumable", "qtyPerUnit": 1},
            ],
            "operations": [
                {"opNo": 10, "stationId": "station2", "operationName": "Kutu Koy", "standardTimeSec": 12},
                {"opNo": 20, "stationId": "station2", "operationName": "Kullanim Kilavuzu Koy", "standardTimeSec": 8},
                {"opNo": 30, "stationId": "station2", "operationName": "Paketi Kapat", "standardTimeSec": 15},
                {"opNo": 40, "stationId": "station2", "operationName": "Bantla", "standardTimeSec": 10},
            ],
        }

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

    def test_kiosk_package_endpoints_complete_station2_final_product(self) -> None:
        client, config, manager, store, runtime_service = self._build_client()
        manager.import_work_orders([self._sample_package_work_order()])
        manager.apply_control("shift_start")
        manager.start_work_order("WO-PKT-A-001", operator_code="OP-PKG")
        store.refresh_oee_runtime_state(config.module_id, force=True)

        start = client.post(
            f"/api/modules/{config.module_id}/kiosk/packages/start",
            json={"device_id": "kiosk-1", "operator_id": "1"},
        )
        finish = client.post(
            f"/api/modules/{config.module_id}/kiosk/packages/finish",
            json={"device_id": "kiosk-1", "operator_id": "1"},
        )
        quality = client.post(
            f"/api/modules/{config.module_id}/kiosk/packages/quality",
            json={"device_id": "kiosk-1", "operator_id": "1", "quality": "GOOD"},
        )

        self.assertEqual(start.status_code, 200)
        self.assertEqual(finish.status_code, 200)
        self.assertEqual(quality.status_code, 200)
        self.assertEqual(start.json()["cycle"]["cycleId"], "PKG-WO-PKT-A-001-0001")
        state = manager.read_state()
        self.assertEqual(state["counts"]["total"], 1)
        self.assertEqual(state["counts"]["good"], 1)
        self.assertEqual(state["workOrders"]["ordersById"]["WO-PKT-A-001"]["completedQty"], 1)
        event_types = [row[0] for row in runtime_service.excel_sink.kiosk_events]
        self.assertIn("station2_package_started", event_types)
        self.assertIn("station2_package_finished", event_types)
        self.assertIn("station2_quality_good", event_types)

    def test_kiosk_package_endpoint_error_codes_are_explicit(self) -> None:
        client, config, manager, store, _runtime_service = self._build_client()

        no_shift = client.post(
            f"/api/modules/{config.module_id}/kiosk/packages/start",
            json={"device_id": "kiosk-1", "operator_id": "1"},
        )
        self.assertEqual(no_shift.status_code, 409)
        self.assertEqual(no_shift.json()["detail"], "SHIFT_NOT_ACTIVE")

        manager.apply_control("shift_start")
        store.refresh_oee_runtime_state(config.module_id, force=True)
        no_order = client.post(
            f"/api/modules/{config.module_id}/kiosk/packages/start",
            json={"device_id": "kiosk-1", "operator_id": "1"},
        )
        self.assertEqual(no_order.status_code, 400)
        self.assertEqual(no_order.json()["detail"], "WORK_ORDER_NOT_FOUND")

        manager.import_work_orders([self._sample_package_work_order()])
        manager.start_work_order("WO-PKT-A-001", operator_code="OP-PKG")
        active_missing = client.post(
            f"/api/modules/{config.module_id}/kiosk/packages/finish",
            json={"device_id": "kiosk-1", "operator_id": "1"},
        )
        self.assertEqual(active_missing.status_code, 409)
        self.assertEqual(active_missing.json()["detail"], "PACKAGE_ACTIVE_NOT_FOUND")

        start = client.post(
            f"/api/modules/{config.module_id}/kiosk/packages/start",
            json={"device_id": "kiosk-1", "operator_id": "1"},
        )
        self.assertEqual(start.status_code, 200)
        repeat_start = client.post(
            f"/api/modules/{config.module_id}/kiosk/packages/start",
            json={"device_id": "kiosk-1", "operator_id": "1"},
        )
        self.assertEqual(repeat_start.status_code, 409)
        self.assertEqual(repeat_start.json()["detail"], "PACKAGE_ACTIVE_EXISTS")

        finish = client.post(
            f"/api/modules/{config.module_id}/kiosk/packages/finish",
            json={"device_id": "kiosk-1", "operator_id": "1"},
        )
        self.assertEqual(finish.status_code, 200)
        bad_quality = client.post(
            f"/api/modules/{config.module_id}/kiosk/packages/quality",
            json={"device_id": "kiosk-1", "operator_id": "1", "quality": "BAD"},
        )
        self.assertEqual(bad_quality.status_code, 400)
        self.assertEqual(bad_quality.json()["detail"], "INVALID_PACKAGE_QUALITY")
        quality = client.post(
            f"/api/modules/{config.module_id}/kiosk/packages/quality",
            json={"device_id": "kiosk-1", "operator_id": "1", "quality": "SCRAP"},
        )
        self.assertEqual(quality.status_code, 200)
        repeat_quality = client.post(
            f"/api/modules/{config.module_id}/kiosk/packages/quality",
            json={
                "device_id": "kiosk-1",
                "operator_id": "1",
                "quality": "GOOD",
                "package_cycle_id": finish.json()["cycle"]["cycleId"],
            },
        )
        self.assertEqual(repeat_quality.status_code, 409)
        self.assertEqual(repeat_quality.json()["detail"], "PACKAGE_CYCLE_ALREADY_FINALIZED")

    def test_kiosk_bootstrap_exposes_package_recipe_and_station_buffer_warning(self) -> None:
        client, config, manager, store, _runtime_service = self._build_client()
        manager.import_work_orders([self._sample_package_work_order()])
        manager.apply_control("shift_start")
        manager.start_work_order("WO-PKT-A-001", operator_code="OP-PKG")
        manager.apply_mega_log(
            "MEGA|AUTO|QUEUE=ENQ|ITEM_ID=101|MEASURE_ID=101|COLOR=KIRMIZI|DECISION_SOURCE=CORE_STABLE|TRAVEL_MS=100|PENDING=1",
            "2026-04-02T08:01:00Z",
        )
        manager.apply_mega_log("MEGA|ROBOT|EVENT=RELEASED|ITEM_ID=101|MEASURE_ID=101|TRIGGER=TIMER", "2026-04-02T08:01:01Z")
        manager.apply_mega_log(
            "MEGA|AUTO|QUEUE=ENQ|ITEM_ID=102|MEASURE_ID=102|COLOR=SARI|DECISION_SOURCE=CORE_STABLE|TRAVEL_MS=100|PENDING=1",
            "2026-04-02T08:01:02Z",
        )
        manager.apply_mega_log("MEGA|ROBOT|EVENT=RELEASED|ITEM_ID=102|MEASURE_ID=102|TRIGGER=TIMER", "2026-04-02T08:01:03Z")
        store.refresh_oee_runtime_state(config.module_id, force=True)

        response = client.get(f"/api/modules/{config.module_id}/kiosk/bootstrap", params={"device_id": "kiosk-1"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        active_order = payload["work_orders"]["active_order"]
        self.assertEqual(active_order["order_id"], "WO-PKT-A-001")
        self.assertEqual(active_order["qty"], 3)
        self.assertEqual(active_order["requirements"][0]["item_type"], "box")
        self.assertEqual(payload["package"]["counters"]["target"], 3)
        self.assertTrue(payload["package"]["recipe_ready"])
        self.assertTrue(payload["package"]["can_start"])
        self.assertEqual(payload["package"]["buffer_warning"]["level"], "ok")
        self.assertEqual(payload["package"]["buffer_warning"]["observed_by_color"]["red"], 1)
        self.assertEqual(payload["package"]["buffer_warning"]["observed_by_color"]["yellow"], 1)

    def test_kiosk_package_panel_uses_next_package_recipe_while_component_order_is_active(self) -> None:
        client, config, manager, store, _runtime_service = self._build_client()
        manager.import_work_orders(
            [
                {
                    "order_id": "WO-RED-COMPONENT",
                    "stock_code": "BOX-RED",
                    "stock_name": "Kirmizi Kutu",
                    "qty": 1,
                    "color": "red",
                    "cycle_time_sec": 15,
                },
                self._sample_package_work_order(),
            ]
        )
        manager.apply_control("shift_start")
        manager.start_work_order("WO-RED-COMPONENT", operator_code="OP-BOX")
        store.refresh_oee_runtime_state(config.module_id, force=True)

        response = client.get(f"/api/modules/{config.module_id}/kiosk/bootstrap", params={"device_id": "kiosk-1"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["work_orders"]["active_order"]["order_id"], "WO-RED-COMPONENT")
        self.assertFalse(payload["package"]["recipe_ready"])
        self.assertTrue(payload["package"]["display_recipe_ready"])
        self.assertEqual(payload["package"]["display_order"]["order_id"], "WO-PKT-A-001")
        self.assertNotIn("materials", payload["package"]["buffer_warning"]["message"])
        self.assertIn("paket is emrini baslatin", payload["package"]["buffer_warning"]["message"])
        self.assertEqual(
            [row["operation_name"] for row in payload["package"]["display_order"]["operations"]],
            ["Kutu Koy", "Kullanim Kilavuzu Koy", "Paketi Kapat", "Bantla"],
        )

    def test_kiosk_bootstrap_shows_station1_transfer_quality_candidate_without_final_oee_count(self) -> None:
        client, config, manager, _store, _runtime_service = self._build_client()
        manager.apply_control("shift_start", now=datetime(2026, 4, 2, 8, 0, 0, tzinfo=timezone(timedelta(hours=3))))
        manager.import_work_orders(
            [
                {
                    "order_id": "WO-RED-COMPONENT",
                    "stock_code": "BOX-RED",
                    "stock_name": "Kirmizi Kutu",
                    "qty": 1,
                    "color": "red",
                    "cycle_time_sec": 15,
                }
            ]
        )
        manager.start_work_order("WO-RED-COMPONENT", operator_code="OP-BOX")
        manager.apply_mega_log(
            "MEGA|AUTO|QUEUE=ENQ|ITEM_ID=501|MEASURE_ID=51|COLOR=KIRMIZI|DECISION_SOURCE=CORE_STABLE|TRAVEL_MS=4500|PENDING=1",
            "2026-04-02T08:02:00+03:00",
        )
        manager.apply_mega_log(
            "MEGA|ROBOT|EVENT=RELEASED|ITEM_ID=501|MEASURE_ID=51|TRIGGER=TIMER",
            "2026-04-02T08:02:03+03:00",
        )

        response = client.get(f"/api/modules/{config.module_id}/kiosk/bootstrap", params={"device_id": "kiosk-1"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["line_status"]["production"]["total"], 0)
        self.assertEqual(payload["recent_items"][0]["item_id"], "501")
        self.assertTrue(payload["recent_items"][0]["can_override"])
        self.assertEqual(payload["recent_items"][0]["oee_scope"], "station1_component_transfer")
        active_order = payload["work_orders"]["active_order"]
        self.assertEqual(active_order["order_id"], "WO-RED-COMPONENT")
        self.assertEqual(active_order["status"], "pending_approval")

    def test_work_order_folder_reload_skips_slow_ferp_label_validation(self) -> None:
        client, config, manager, _store, _runtime_service = self._build_client()

        with patch.object(manager, "import_work_orders_from_file", wraps=manager.import_work_orders_from_file) as import_mock:
            response = client.post(f"/api/modules/{config.module_id}/work-orders/reload", json={})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(import_mock.called)
        self.assertFalse(import_mock.call_args.kwargs["validate_ferp_labels"])

    def test_kiosk_package_start_requires_package_recipe_in_active_order(self) -> None:
        client, config, manager, store, _runtime_service = self._build_client()
        manager.import_work_orders(
            [
                {
                    "order_id": "WO-LEGACY-BOX",
                    "stock_code": "BOX-RED",
                    "stock_name": "Kirmizi Kutu",
                    "qty": 1,
                    "color": "red",
                    "cycle_time_sec": 15,
                }
            ]
        )
        manager.apply_control("shift_start")
        manager.start_work_order("WO-LEGACY-BOX", operator_code="OP-BOX")
        store.refresh_oee_runtime_state(config.module_id, force=True)

        response = client.get(f"/api/modules/{config.module_id}/kiosk/bootstrap", params={"device_id": "kiosk-1"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["package"]["recipe_ready"])
        self.assertFalse(payload["package"]["can_start"])
        self.assertEqual(payload["package"]["buffer_warning"]["level"], "warning")
        self.assertNotIn("materials", payload["package"]["recipe_message"])
        self.assertIn("paketleme is emri degil", payload["package"]["recipe_message"])

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


if __name__ == "__main__":
    unittest.main()

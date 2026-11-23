from __future__ import annotations

import os
import tempfile
import unittest
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
    def _build_client(self, host="127.0.0.1", cutting_enabled=False, kiosk_password=""):
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
                "MES_WEB_CUTTING_WORKFLOW_ENABLED": "1" if cutting_enabled else "0",
                "MES_WEB_KIOSK_DESIGN_PASSWORD": kiosk_password,
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

        async def app_with_client(scope, receive, send):
            await app({**scope, "client": (host, 50000)}, receive, send)

        client = TestClient(app_with_client, base_url="http://127.0.0.1:8080")
        self.addCleanup(client.close)
        return client, config, manager, store, runtime_service

    def test_kiosk_designer_pins_running_work_to_a_published_revision(self) -> None:
        client, _config, manager, _store, runtime = self._build_client(kiosk_password="test-kiosk-only")
        manager.import_work_orders([{"orderId": "IE-10", "stockCode": "BOX", "quantity": 10}])
        manager.start_work_order("IE-10")
        auth = ("muhendis", "test-kiosk-only")
        designer = "/api/kiosk-designs/kontrol"
        board = "/api/station-kiosks/kontrol"
        first = {
            "title": "Görsel Kontrol", "instructions": "Yüzeyi kontrol et.",
            "timer": True, "show_target": True, "result_options": ["Sağlam", "Yeniden işlem"],
            "steps": [{"label": "Yüzey kontrol edildi", "kind": "check", "required": True, "options": []}],
            "sections": [{"title": "Hatırlatma", "body": "Parti etiketini kontrol et."}],
        }
        self.assertEqual(client.get("/kiosk-tasarla").status_code, 401)
        self.assertEqual(client.get("/kiosk-tasarla", auth=auth).status_code, 200)
        self.assertEqual(client.put(designer, json={"revision": 0, "design": first}).status_code, 401)
        draft = client.put(designer, auth=auth, json={"revision": 0, "design": first})
        self.assertEqual(draft.status_code, 200, draft.text)
        revision = draft.json()["revision"]
        self.assertEqual(client.put(designer, auth=auth, json={"revision": 0, "design": first}).json()["revision"], revision)
        self.assertEqual(client.get(board).status_code, 404)
        self.assertEqual(client.get("/istasyon/kontrol").status_code, 404)
        self.assertEqual(client.post(f"{designer}/publish", auth=auth, json={"revision": revision}).json()["published"], 1)
        self.assertEqual(client.get("/istasyon/kontrol").status_code, 200)
        original = client.get(board).json()
        self.assertEqual(original["order"]["quantity"], 10)
        start = {"run_id": "test-run-1", "operator": "Deneme Operatörü", "order_id": "IE-10", "order_key": original["order"]["key"], "version": 1}
        self.assertEqual(client.post(f"{board}/start", json=start).status_code, 200)
        self.assertEqual(client.post(f"{board}/start", json=start).status_code, 200)
        second = {**first, "instructions": "Yeni talimat", "steps": [{"label": "Ölçü", "kind": "number", "required": True, "options": []}]}
        revised = client.put(designer, auth=auth, json={"revision": revision, "design": second}).json()["revision"]
        self.assertEqual(client.post(f"{designer}/publish", auth=auth, json={"revision": revision}).status_code, 409)
        self.assertEqual(client.post(f"{designer}/publish", auth=auth, json={"revision": revised}).json()["published"], 2)
        self.assertEqual(client.get(board).json()["design"]["instructions"], first["instructions"])
        self.assertEqual(client.get(board).json()["active"]["version"], 1)
        finish = {"run_id": "test-run-1", "values": [False], "result": "Sağlam"}
        self.assertEqual(client.post(f"{board}/finish", json=finish).status_code, 422)
        self.assertEqual(client.post(f"{board}/finish", json={**finish, "values": [True]}).status_code, 200)
        self.assertEqual(client.post(f"{board}/finish", json={**finish, "values": [True]}).status_code, 200)
        self.assertEqual(client.get(board).json()["version"], 2)
        self.assertEqual(client.get("/api/kiosk-designs", auth=auth).json()[0]["last_completed"]["result"], "Sağlam")
        self.assertEqual(len(manager.read_state()["stationKiosks"]["kontrol"]["completed"]), 1)
        self.assertEqual(manager.read_state()["workOrders"]["ordersById"]["IE-10"]["completedQty"], 0)
        self.assertEqual(runtime.mqtt_client.published, [])

    def test_kiosk_designer_rejects_remote_editor_and_station_access(self) -> None:
        client, *_ = self._build_client(host="192.0.2.20", kiosk_password="test-kiosk-only")
        auth = ("muhendis", "test-kiosk-only")
        self.assertEqual(client.get("/kiosk-tasarla", auth=auth).status_code, 403)
        self.assertEqual(client.get("/api/station-kiosks/kontrol").status_code, 403)

    def test_manual_coating_counts_partial_batches_without_counting_line_output(self) -> None:
        client, config, manager, _store, runtime = self._build_client()
        manager.import_work_orders([{"orderId": "IE-10", "stockCode": "BOX", "quantity": 10}])
        manager.start_work_order("IE-10")
        url = "/api/manual-coating"
        self.assertEqual(client.get("/kaplama").status_code, 200)
        progress = client.get(url).json()["progress"]
        self.assertEqual((progress["completed_qty"], progress["target_qty"]), (0, 10))
        batch = {
            "order_id": "IE-10", "order_key": progress["order_key"],
            "operator": "Ayşe", "quantity": 5, "request_id": "batch-1",
        }

        foreign = client.post(url, json=batch, headers={"Origin": "https://other.example"})
        self.assertEqual(foreign.status_code, 403)
        missing_type = client.post(url, content=(
            '{"request_id":"batch-1","order_id":"IE-10","order_key":"","operator":"Test","quantity":5}'
        ))
        self.assertIn(missing_type.status_code, {415, 422})
        self.assertEqual(manager.read_state()["manualCoatingRecords"], {})

        response = client.post(url, json=batch, headers={"Origin": "http://127.0.0.1:8080"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["progress"]["completed_qty"], 5)
        self.assertFalse(response.json()["progress"]["complete"])
        manager.import_work_orders([{"orderId": "IE-10", "stockCode": "BOX", "quantity": 10, "queuedAt": "2026-01-01"}])
        self.assertTrue(client.post(url, json=batch).json()["duplicate"])
        self.assertEqual(client.get(url).json()["progress"]["completed_qty"], 5)
        self.assertEqual(client.post(url, json={**batch, "quantity": 4}).status_code, 409)
        self.assertEqual(client.post(url, json={**batch, "request_id": "excess", "quantity": 6}).status_code, 409)
        self.assertEqual(client.post(url, json={**batch, "request_id": "invalid", "quantity": True}).status_code, 422)
        self.assertEqual(client.post(url, json={**batch, "request_id": "wrong", "order_id": "IE-old"}).status_code, 409)

        dashboard = client.get(f"/api/modules/{config.module_id}/dashboard").json()
        self.assertEqual(dashboard["work_orders"]["manual_coating"]["completed_qty"], 5)
        next_batch = client.post(url, json={**batch, "request_id": "batch-2"}).json()["progress"]
        self.assertEqual(next_batch["completed_qty"], 10)
        self.assertTrue(next_batch["complete"])
        state = manager.read_state()
        self.assertEqual(len(state["manualCoatingRecords"]), 2)
        self.assertEqual(state["workOrders"]["ordersById"]["IE-10"]["completedQty"], 0)
        self.assertEqual(state["workOrders"]["ordersById"]["IE-10"]["status"], "active")
        self.assertEqual(runtime.mqtt_client.published, [])

        manager.reset_work_orders()
        manager.import_work_orders([{"orderId": "IE-10", "stockCode": "BOX", "quantity": 10, "queuedAt": "2026-01-01"}])
        manager.start_work_order("IE-10")
        self.assertEqual(client.get(url).json()["progress"]["completed_qty"], 0)
        self.assertTrue(client.post(url, json=batch).json()["duplicate"])
        self.assertEqual(client.post(url, json={**batch, "request_id": "stale-order"}).status_code, 409)

        manager.import_work_orders([{"orderId": "IE-10", "stockCode": "BOX", "quantity": 10, "unit": "KG"}])
        progress = client.get(url).json()["progress"]
        self.assertFalse(progress["unit_supported"])
        response = client.post(url, json={**batch, "request_id": "wrong-unit", "order_key": progress["order_key"]})
        self.assertEqual(response.status_code, 409)

    def test_manual_coating_starts_with_no_order_and_is_local_only(self) -> None:
        client, _config, _manager, _store, _runtime = self._build_client()
        self.assertIsNone(client.get("/api/manual-coating").json()["progress"])
        self.assertEqual(client.get("/giyotin").status_code, 404)
        remote, *_ = self._build_client(host="192.0.2.10")
        self.assertEqual(remote.get("/kaplama").status_code, 403)
        self.assertEqual(remote.get("/api/manual-coating").status_code, 403)
        self.assertEqual(remote.post("/api/manual-coating", json={
            "order_id": "IE-10", "order_key": "", "operator": "Ayşe", "quantity": 5, "request_id": "batch-1",
        }).status_code, 403)

    def test_two_cut_tapes_make_one_box_available_immediately(self) -> None:
        client, config, manager, _store, runtime = self._build_client(cutting_enabled=True)
        manager.import_work_orders([{"orderId": "IE-10", "stockCode": "BOX", "quantity": 10}])
        manager.start_work_order("IE-10")
        cutting = "/api/cutting-workflow"
        coating = "/api/manual-coating"
        self.assertEqual(client.get("/giyotin").status_code, 200)
        progress = client.get(coating).json()["progress"]
        batch = {"order_id": "IE-10", "order_key": progress["order_key"], "operator": "Ayşe"}

        def cutting_action(request_id, action, **fields):
            return client.post(cutting, json={**batch, "request_id": request_id, "action": action, **fields})

        self.assertFalse(progress["can_record"])
        first = cutting_action("cut-1", "cut", quantity=1)
        self.assertEqual(first.status_code, 200, first.text)
        summary = first.json()["progress"]["cutting"]
        self.assertEqual((summary["cut_tapes"], summary["target_tapes"], summary["unpaired_tapes"]), (1, 20, 1))
        self.assertTrue(cutting_action("cut-1", "cut", quantity=1).json()["duplicate"])
        with self.assertRaisesRegex(ValueError, "CUTTING_ORDER_TARGET_LOCKED"):
            manager.import_work_orders([{"orderId": "IE-10", "stockCode": "BOX", "quantity": 12}])
        self.assertEqual(client.get(coating).json()["progress"]["target_qty"], 10)
        self.assertFalse(client.get(coating).json()["progress"]["can_record"])
        self.assertEqual(client.post(coating, json={**batch, "request_id": "coat-early", "quantity": 1}).status_code, 409)
        second = cutting_action("cut-2", "cut", quantity=1).json()["progress"]
        self.assertTrue(second["can_record"])
        self.assertEqual(second["cutting"]["available_boxes"], 1)
        self.assertEqual(client.post(coating, json={**batch, "request_id": "over", "quantity": 2}).status_code, 409)
        coat_batch = {**batch, "request_id": "coat-1", "quantity": 1}
        coated = client.post(coating, json=coat_batch)
        self.assertEqual(coated.status_code, 200, coated.text)
        self.assertEqual(coated.json()["progress"]["completed_qty"], 1)
        self.assertFalse(coated.json()["progress"]["can_record"])
        self.assertTrue(client.post(coating, json=coat_batch).json()["duplicate"])
        self.assertEqual(manager.read_state()["manualCoatingRecords"]["coat-1"]["tapes_used"], 2)
        self.assertEqual(cutting_action("cut-3", "cut", quantity=3).json()["progress"]["cutting"]["available_boxes"], 1)
        self.assertEqual(cutting_action("cut-over", "cut", quantity=16).status_code, 409)
        dashboard = client.get(f"/api/modules/{config.module_id}/dashboard").json()["work_orders"]
        self.assertEqual(dashboard["manual_coating"]["cutting"]["cut_tapes"], 5)
        self.assertEqual(cutting_action("cut-last", "cut", quantity=15).json()["progress"]["cutting"]["available_boxes"], 9)
        finished = client.post(coating, json={**batch, "request_id": "coat-last", "quantity": 9}).json()["progress"]
        self.assertTrue(finished["complete"])
        self.assertEqual(finished["completed_qty"], 10)
        self.assertEqual(manager.read_state()["workOrders"]["ordersById"]["IE-10"]["completedQty"], 0)
        self.assertEqual(runtime.mqtt_client.published, [])

    def test_cutting_progress_does_not_transfer_to_another_work_order(self) -> None:
        client, _config, manager, _store, _runtime = self._build_client(cutting_enabled=True)
        manager.import_work_orders([
            {"orderId": "IE-1", "stockCode": "BOX", "quantity": 10},
            {"orderId": "IE-2", "stockCode": "BOX", "quantity": 10},
        ])
        manager.start_work_order("IE-1")
        url = "/api/cutting-workflow"

        def active_batch():
            current = client.get("/api/manual-coating").json()["progress"]
            return {"order_id": current["order_id"], "order_key": current["order_key"], "operator": "Ayşe"}

        batch_one = active_batch()
        self.assertEqual(client.post(url, json={**batch_one, "request_id": "cut-a", "action": "cut", "quantity": 2}).status_code, 200)
        manager.rollback_active_work_order()
        manager.start_work_order("IE-2")
        self.assertEqual(client.get("/api/manual-coating").json()["progress"]["cutting"]["available_boxes"], 0)
        self.assertEqual(client.post(url, json={**batch_one, "request_id": "late-cut", "action": "cut", "quantity": 2}).status_code, 409)
        manager.rollback_active_work_order()
        manager.start_work_order("IE-1")
        self.assertEqual(client.get("/api/manual-coating").json()["progress"]["cutting"]["available_boxes"], 1)

    def test_old_lot_records_are_preserved_without_becoming_ready_tape(self) -> None:
        client, _config, manager, _store, _runtime = self._build_client(cutting_enabled=True)
        manager.import_work_orders([{"orderId": "IE-1", "stockCode": "BOX", "quantity": 10}])
        manager.start_work_order("IE-1")
        progress = client.get("/api/manual-coating").json()["progress"]
        key = progress["order_key"]
        old_lot = {"cut_qty": 5, "status": "parked", "lot_id": "OLD-LOT"}
        action = {"operation": "cut", "order_id": "IE-1", "order_key": key, "operator": "Ayşe", "lot_id": "", "quantity": 5}
        state = manager.read_state()
        state["cuttingWorkflow"]["batches"]["IE-1"] = {key: old_lot}
        state["cuttingWorkflow"]["receipts"]["old-cut"] = {"action": action}
        manager.write_state(state)
        current = client.get("/api/manual-coating").json()["progress"]
        self.assertFalse(current["can_record"])
        self.assertTrue(current["cutting"]["legacy_blocked"])
        request = {"order_id": "IE-1", "order_key": key, "operator": "Ayşe", "quantity": 5}
        replay = client.post("/api/cutting-workflow", json={**request, "request_id": "old-cut"})
        self.assertTrue(replay.json()["duplicate"])
        self.assertEqual(client.post("/api/cutting-workflow", json={**request, "request_id": "new-cut"}).status_code, 409)
        self.assertEqual(manager.read_state()["cuttingWorkflow"]["batches"]["IE-1"][key], old_lot)

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

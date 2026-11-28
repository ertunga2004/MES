from datetime import datetime, timezone
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from mes_web import app as app_module
from mes_web.config import AppConfig
from mes_web.excel_runtime import ExcelRuntimeSink
from mes_web.giyotin_runtime import GiyotinError, GiyotinRuntime
from mes_web.manual_coating import manual_coating_progress
from mes_web.mqtt_runtime import MqttIngestClient
from mes_web.oee_state import OeeRuntimeStateManager


LINKS = dict(wifi_connected=True, mqtt_connected=True, nano_connected=True, dropped_publish=0)
IDLE = dict(nano_ready=True, cycle_busy=False, permit_active=False, event_pending=False, nano_state="PERMIT_REQUIRED")


class GiyotinTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(TemporaryDirectory())
        self.manager = OeeRuntimeStateManager(Path(folder) / "state.json")
        self.manager.import_work_orders([{"orderId": key, "stockCode": "BOX", "quantity": 1} for key in ("IE-1", "IE-2")])
        self.manager.start_work_order("IE-1")
        self.config = AppConfig(giyotin_protocol4_enabled=True)
        self.shift = {"operator": "Operatör", "startedAt": 1000}
        self.sent = []
        self.now = 0
        self.runtime = self.new_runtime()
        self.session = "esp-A"

    def new_runtime(self):
        return GiyotinRuntime(self.config, self.manager, lambda: self.shift, self.publish, clock=lambda: self.now)

    def publish(self, payload):
        # Prove the binding and the completed event are durable before any outgoing write.
        data = self.protocol()
        if payload.get("permit") == 1:
            self.assertIn(f'{payload["session_id"]}:{payload["permit_id"]}', data["permits"])
        if "event_ack_id" in payload:
            self.assertIn(payload["event_ack_id"], data["events"])
            self.assertFalse(data["events"][payload["event_ack_id"]].get("unresolved"))
        self.sent.append(payload)

    def protocol(self):
        return self.manager.read_state()["cuttingWorkflow"]["protocol4"]

    def board(self):
        return self.runtime.board(self.shift)

    def message(self, topic, payload, *, retained=False):
        self.runtime.handle(topic, json.dumps(payload), datetime.now(timezone.utc).isoformat(), retained=retained)

    def link(self):
        self.message("heartbeat", {"protocol": 4, "session_id": self.session})
        self.message("bridge_status", LINKS)
        self.message("status", IDLE)

    def start(self):
        order = self.board()["order"]
        self.runtime.control("giyotin-start", {"orderId": order["id"], "orderKey": order["key"]})
        return self.writes()[-1]["permit_id"]

    def writes(self):
        return [row for row in self.sent if row.get("action") == "PERMIT"]

    def ack(self, number, permit):
        self.message("logs", {"event": "NANO_ACK", "nano_line": f"ACK|PERMIT|permit_id={number}|permit={permit}"})

    def event(self, kind, number, *, session=None):
        original = session or self.session
        event_id = f"{original}:{number}"
        self.message("logs", {"event": kind, "event_id": event_id, "permit_id": number, "at_uptime_ms": 999})
        return event_id

    def test_live_telemetry_and_matching_ack_gate_the_single_cycle(self):
        for topic, payload in (("heartbeat", {"session_id": self.session, "protocol": 4}),
                               ("bridge_status", LINKS), ("status", IDLE)):
            self.message(topic, payload, retained=True)
        self.assertFalse(self.board()["online"])
        with self.assertRaisesRegex(GiyotinError, "offline"):
            self.start()
        self.message("heartbeat", {"session_id": self.session, "protocol": 3})
        self.assertEqual(self.sent, [])
        self.link()
        first = self.start()
        self.assertEqual(self.writes(), [{"action": "PERMIT", "session_id": self.session, "permit_id": 1, "permit": 1}])
        self.assertIs(type(self.writes()[0]["permit"]), int)
        self.message("status", {**IDLE, "nano_state": "WAIT_RELEASE", "permit_active": True})
        self.ack(first + 9, 1)
        self.assertEqual(self.board()["mode"], "awaiting_permit")
        self.ack(first, 1)
        self.assertEqual(self.board()["mode"], "permitted")
        self.event("CUT_START", first)
        self.assertEqual(self.board()["order"]["completed"], 0)
        self.assertEqual(self.board()["mode"], "running")
        event_id = self.event("CUT_DONE", first)
        self.assertIn({"session_id": self.session, "event_ack_id": event_id}, self.sent)
        self.event("CUT_DONE", first)
        self.assertEqual(self.board()["order"]["completed"], 1)
        self.assertEqual(len(self.writes()), 1)
        self.message("status", {**IDLE, "event_pending": True, "nano_state": "EVENT_PENDING"})
        self.assertEqual(len(self.writes()), 1)
        self.message("status", IDLE)
        self.assertEqual(self.writes()[-1]["permit_id"], first + 1)
        second = self.writes()[-1]["permit_id"]
        self.event("CUT_DONE", second)
        self.assertEqual(self.writes()[-1]["permit"], 0)
        self.assertEqual(self.board()["mode"], "revoking")
        self.ack(second + 1, 0)
        self.message("status", IDLE)
        self.assertFalse(self.board()["canStart"])
        progress = manual_coating_progress(self.manager.read_state(), cutting_enabled=True)
        self.assertEqual(progress["cutting"]["available_boxes"], 1)

    def test_late_event_after_order_change_and_reconnect_uses_issued_order(self):
        self.link()
        first = self.start()
        self.event("CUT_START", first)
        self.manager.rollback_active_work_order()
        self.manager.start_work_order("IE-2", transition_reason="test switch")
        self.runtime.tick()
        self.assertEqual(self.writes()[-1]["permit"], 0)
        self.session = "esp-B"
        self.link()
        event_id = self.event("CUT_DONE", first, session="esp-A")
        self.assertEqual(self.protocol()["events"][event_id]["orderId"], "IE-1")
        self.assertIn({"session_id": "esp-B", "event_ack_id": event_id}, self.sent)
        self.assertEqual(self.board()["order"]["completed"], 0)
        self.assertEqual(self.board()["mode"], "review")
        review = self.board()["review"]
        self.runtime.control("giyotin-reconcile", {"reviewId": review["id"], "outcome": "no_credit", "confirmed": True})
        self.assertEqual(self.protocol()["events"][event_id]["count"], 1)

    def test_restart_and_calibration_share_persistent_sequence(self):
        self.link()
        settings = {"home_angle": 150, "cycle_angle": 0, "servo_speed_dps": 150}
        with self.assertRaisesRegex(GiyotinError, "invalid_calibration"):
            self.runtime.control("giyotin-calibrate", {**settings, "home_angle": True})
        self.runtime.control("giyotin-calibrate", settings)
        self.assertEqual(self.sent[-1], {"action": "CALIBRATE", "session_id": self.session, "command_id": 1, **settings})
        self.message("logs", {"event": "NANO_ACK", "nano_line": "ACK|CALIBRATE|revision=2"})
        self.assertEqual(self.board()["calibration"], "pending")
        self.message("status", {**IDLE, **settings, "config_revision": "2"})
        self.assertEqual(self.board()["calibration"], "confirmed")
        self.assertEqual(self.start(), 2)
        self.runtime = self.new_runtime()
        self.link()
        self.assertEqual(self.board()["mode"], "review")
        self.assertEqual(self.writes()[-1]["permit"], 0)
        self.assertEqual(self.writes()[-1]["permit_id"], 3)

    def test_pause_requires_new_operator_confirmation_and_revoke_ack(self):
        self.link()
        first = self.start()
        self.runtime.control("giyotin-pause", {})
        self.message("status", IDLE)
        self.assertFalse(self.board()["canStart"])
        self.ack(first + 1, 0)
        self.assertTrue(self.board()["canStart"])
        self.assertEqual(self.start(), first + 2)
        self.shift = None
        self.runtime.tick()
        self.assertEqual(self.writes()[-1]["permit"], 0)

    def test_expiry_and_nano_reset_stop_automatic_grants(self):
        self.link()
        first = self.start()
        self.ack(first, 1)
        self.message("status", {**IDLE, "nano_state": "READY", "permit_active": True})
        self.now = 8
        self.message("heartbeat", {"session_id": self.session, "protocol": 4})
        self.now = 15
        self.message("status", IDLE)
        self.assertEqual(self.writes()[-1]["permit"], 0)
        self.ack(first + 1, 0)
        self.message("status", IDLE)
        self.assertEqual(self.board()["reason"], "permit_expired")
        self.assertEqual(len(self.writes()), 2)
        self.start()
        self.message("logs", {"event": "NANO_BOOT"})
        self.assertEqual(self.board()["mode"], "review")
        self.assertEqual(self.board()["order"]["completed"], 0)

    def test_uncertain_cycle_requires_explicit_reconciliation_and_no_double_credit(self):
        self.link()
        first = self.start()
        self.message("status", {**IDLE, "nano_state": "CYCLE_UNCERTAIN"})
        event_id = self.event("CYCLE_UNCERTAIN", first)
        self.assertEqual(self.board()["order"]["completed"], 0)
        self.assertFalse(any(row.get("event_ack_id") == event_id for row in self.sent))
        review = self.board()["review"]
        with self.assertRaisesRegex(GiyotinError, "invalid_resolution"):
            self.runtime.control("giyotin-reconcile", {"reviewId": review["id"], "outcome": "completed"})
        self.runtime.control("giyotin-reconcile", {"reviewId": review["id"], "outcome": "completed", "confirmed": True})
        self.assertTrue(any(row.get("event_ack_id") == event_id for row in self.sent))
        self.event("CUT_DONE", first)
        self.assertEqual(self.board()["order"]["completed"], 1)
        self.assertEqual(len(self.runtime.production_records()), 1)

    def test_lost_bridge_publications_request_status_and_block_rearming(self):
        self.link()
        self.start()
        self.sent.clear()
        self.message("bridge_status", {**LINKS, "dropped_publish": 1})
        self.assertIn({"action": "STATUS"}, self.sent)
        self.assertFalse(self.board()["canStart"])
        self.assertEqual(self.board()["review"]["reason"], "telemetry_loss")

    def test_completion_is_replayed_after_persistence_failure(self):
        self.link()
        first = self.start()
        self.event("CUT_START", first)
        with patch.object(self.manager, "write_state", side_effect=OSError("test write failure")):
            with self.assertRaises(OSError):
                self.event("CUT_DONE", first)
        self.assertFalse(any("event_ack_id" in row for row in self.sent))
        self.assertEqual(self.board()["order"]["completed"], 0)
        self.event("CUT_DONE", first)
        self.assertEqual(self.board()["order"]["completed"], 1)
        self.assertTrue(any("event_ack_id" in row for row in self.sent))

    def test_station_order_ids_and_quantities_reach_excel_once(self):
        order = {
            "order_id": "ATOLYE-1", "stock_code": "BOX", "quantity": 1, "unit": "adet",
            "station_orders": [
                {"station_code": "giyotin", "station_order_id": "ATOLYE-1-KES", "target_qty": 2, "unit": "adet"},
                {"station_code": "kaplama", "station_order_id": "ATOLYE-1-KAP", "target_qty": 1, "unit": "adet"},
            ],
        }
        self.manager.import_work_orders([order], replace_existing=False)
        self.manager.rollback_active_work_order()
        self.manager.start_work_order("ATOLYE-1")
        self.manager.import_work_orders([order], replace_existing=False)
        state = self.manager.read_state()
        self.assertEqual(state["workOrders"]["orderSequence"].count("ATOLYE-1"), 1)
        with self.assertRaisesRegex(ValueError, "STATION_ORDER_ID_CONFLICT"):
            self.manager.import_work_orders([{**order, "order_id": "ATOLYE-2"}], replace_existing=False)
        workbook_path = self.manager.path.parent / "acceptance.xlsx"
        self.enterContext(patch.dict(os.environ, {"MES_WEB_EXCEL_WORKBOOK_PATH": str(workbook_path)}))
        config = AppConfig(excel_flush_interval_sec=0.01)
        sink = ExcelRuntimeSink(config)
        sink.start()

        def project(stamp):
            sink.record_work_order_state(self.manager.read_state(), stamp)

        self.runtime.on_production = project
        try:
            self.link()
            self.assertEqual(self.board()["order"]["stationOrderId"], "ATOLYE-1-KES")
            self.assertEqual(self.board()["order"]["target"], 2)
            first = self.start()
            first_event = self.event("CUT_DONE", first)
            self.event("CUT_DONE", first)
            self.message("status", IDLE)
            second = self.writes()[-1]["permit_id"]
            self.assertNotEqual(first, second)
            second_event = self.event("CUT_DONE", second)
            progress = manual_coating_progress(self.manager.read_state(), cutting_enabled=True)
            self.assertEqual(progress["station_order"]["station_order_id"], "ATOLYE-1-KAP")
            batch = {
                "request_id": "kaplama-1", "order_id": "ATOLYE-1", "order_key": progress["order_key"],
                "operator": "Operatör", "quantity": 1, "cutting_enabled": True,
            }
            for duplicate in (False, True):
                self.assertEqual(self.manager.record_manual_coating(**batch)["duplicate"], duplicate)
                project(datetime.now(timezone.utc).isoformat())
        finally:
            sink.stop()

        restarted = ExcelRuntimeSink(config)
        restarted.start()
        try:
            restarted.record_work_order_state(self.manager.read_state(), datetime.now(timezone.utc).isoformat())
        finally:
            restarted.stop()
        workbook = load_workbook(workbook_path)
        try:
            headers, *values = workbook["1_Olay_Logu"].values
            rows = [dict(zip(headers, row)) for row in values if row[headers.index("event_uid")]]
            self.assertEqual(len(rows), 3)
            self.assertEqual(
                {row["event_uid"]: (row["production_order_id"], row["station_order_id"], row["quantity"], row["unit"])
                 for row in rows},
                {f"giyotin:nano:{first_event}": ("ATOLYE-1", "ATOLYE-1-KES", 1, "adet"),
                 f"giyotin:nano:{second_event}": ("ATOLYE-1", "ATOLYE-1-KES", 1, "adet"),
                 "kaplama:manual:kaplama-1": ("ATOLYE-1", "ATOLYE-1-KAP", 1, "adet")},
            )
        finally:
            workbook.close()

    def test_rejected_grant_and_stale_heartbeat_require_review(self):
        self.link()
        first = self.start()
        self.message("logs", {"event": "COMMAND_REJECTED", "permit_id": first, "reason": "INVALID_OR_OLD_PERMIT"})
        self.assertEqual(self.writes()[-1]["permit"], 0)
        self.assertEqual(self.board()["review"]["reason"], "command_rejected")
        self.now = self.config.heartbeat_timeout_sec + 1
        self.runtime.tick()
        self.assertFalse(self.board()["online"])
        self.assertFalse(self.board()["canStart"])

    def test_calibration_recovers_config_required_and_ping_exposes_pong(self):
        self.link()
        self.runtime.control("giyotin-ping", {})
        self.assertEqual(self.sent[-1], {"action": "PING"})
        self.message("logs", {"event": "NANO_PONG"})
        self.assertIsNotNone(self.board()["pongAt"])
        self.message("status", {**IDLE, "nano_ready": False, "nano_state": "CONFIG_REQUIRED"})
        self.runtime.control("giyotin-calibrate", {"home_angle": 150, "cycle_angle": 0, "servo_speed_dps": 150})
        self.assertEqual(self.sent[-1]["action"], "CALIBRATE")
        self.assertEqual(self.board()["calibration"], "pending")

    def test_mqtt_routes_all_five_topics_and_publishes_protocol4_at_qos_zero(self):
        mqtt = MqttIngestClient(self.config, Mock())
        mqtt.giyotin = self.runtime
        client = Mock()
        client.publish.return_value = SimpleNamespace(rc=0)
        mqtt.client, mqtt._mqtt = client, SimpleNamespace(MQTT_ERR_SUCCESS=0)
        mqtt._on_connect(client, None, None, 0)
        for topic in self.config.giyotin_topics:
            client.subscribe.assert_any_call(topic)
        root = self.config.giyotin_topic_root
        with patch.object(self.runtime, "receive_mqtt", wraps=self.runtime.receive_mqtt) as receive:
            mqtt._on_message(client, None, SimpleNamespace(topic=f"{root}/heartbeat", payload=b'{}', retain=True))
            self.assertTrue(receive.call_args.kwargs["retained"])
            self.assertEqual(datetime.fromisoformat(receive.call_args.args[2]).utcoffset().total_seconds(), 0)
        mqtt.publish_giyotin({"action": "PING"})
        client.publish.assert_called_once_with(f"{root}/cmd", '{"action": "PING"}', qos=0, retain=False)
        mqtt._on_message(client, None, SimpleNamespace(topic=self.config.topics["status"], payload=b"conveyor"))
        mqtt.store.apply_status_line.assert_called_once()

    def test_tablet_actions_and_old_manual_endpoint(self):
        env = {"MES_WEB_WORKSPACE_LOCAL_PREVIEW": "1", "MES_WEB_WORKSPACE_ACCESS_ENABLED": "0"}
        service = SimpleNamespace(mqtt_client=SimpleNamespace(publish_giyotin=self.publish),
                                  start=AsyncMock(), stop=AsyncMock())
        with (patch.dict(os.environ, env), patch.object(app_module, "config", self.config),
              patch.object(app_module, "runtime_service", service),
              patch.object(app_module, "oee_state_manager", self.manager),
              TestClient(app_module.create_app(), base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client):
            self.runtime = service.mqtt_client.giyotin
            self.link()
            url = "/api/workspace/tablet/giyotin"
            self.assertIn('data-station="giyotin"', client.get("/giyotin").text)
            order = client.get(url).json()["protocol4"]["order"]
            self.assertEqual(order["id"], "IE-1")
            fields = {"orderId": order["id"], "orderKey": order["key"]}
            start = {"action": "giyotin-start", "fields": fields}
            self.assertEqual(client.post(f"{url}/actions", json=start).status_code, 409)
            response = client.post(f"{url}/actions", json={"action": "shift-start", "fields": {"operator": "Tablet"}})
            self.assertTrue(response.json()["board"]["protocol4"]["canStart"])
            response = client.post(f"{url}/actions", json=start)
            self.assertEqual(response.json()["board"]["protocol4"]["mode"], "awaiting_permit")
            self.assertEqual(client.post(f"{url}/actions", json={"action": "cut"}).status_code, 409)
            manual = {"request_id": "manual", "order_id": order["id"], "order_key": order["key"],
                      "operator": "Tablet", "quantity": 1}
            self.assertEqual(client.post("/api/cutting-workflow", json=manual).status_code, 409)
            response = client.post(f"{url}/actions", json={"action": "shift-end"})
            self.assertIsNone(response.json()["board"]["shift"])
            self.assertEqual(self.writes()[-1]["permit"], 0)


if __name__ == "__main__":
    unittest.main()

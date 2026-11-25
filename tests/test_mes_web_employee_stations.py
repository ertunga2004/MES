import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import test_mes_web_kiosk_app as fixtures


class EmployeeStationsTests(unittest.TestCase):
    def build(self, host="127.0.0.1"):
        client, config, manager, store, runtime = fixtures.KioskAppTests._build_client(
            self, host=host, kiosk_password="test-engineer", cutting_enabled=True, handoff_enabled=True,
        )
        manager.import_work_orders([{"orderId": "IE-10", "stockCode": "BOX", "productColor": "blue", "quantity": 1}])
        manager.start_work_order("IE-10")
        return client, config, manager, store, runtime

    def post(self, client, workspace, request_id, action):
        endpoint = f"/api/employee-stations/{workspace}"
        revision = client.get(endpoint).json()["meta"]["revision"]
        return client.post(endpoint + "/actions", json={"id": request_id, "revision": revision, "action": action})

    def test_station_delivery_packaging_and_read_only_observer(self):
        client, config, manager, _, runtime = self.build()
        config.employee_simulation_enabled = True
        self.assertEqual(client.get("/bantlama").status_code, 200)
        self.assertEqual(client.get("/paketleme").status_code, 200)
        self.assertEqual(client.get("/tekniker").status_code, 200)
        self.assertEqual(client.get("/mühendis").status_code, 401)
        self.assertEqual(client.get("/mühendis", auth=("muhendis", "test-engineer")).status_code, 200)
        self.assertEqual(client.get("/calisan/izle/taping").status_code, 200)
        self.assertEqual(client.get("/calisan/izle/cutting").status_code, 200)
        self.assertTrue(client.get("/api/employee-observer/taping").json()["meta"]["readOnly"])
        self.assertEqual(client.post("/api/employee-observer/taping", json={}).status_code, 405)
        self.assertEqual(client.post("/api/employee-stations/taping/actions", json={
            "id": "station-foreign", "revision": 0, "action": {"type": "seal", "orderId": "IE-10"},
        }).status_code, 403)

        def action(workspace, request_id, action, timestamp):
            with patch("mes_web.employee_stations.now_ms", return_value=timestamp):
                response = self.post(client, workspace, request_id, action)
            self.assertEqual(response.status_code, 200, response.text)
            return response.json()

        moment = 1_800_000_000_000
        action("taping", "shift", {"type": "shift", "operation": "start", "operator": "Bant Operatörü"}, moment)
        action("taping", "box", {"type": "start-box", "color": "blue"}, moment)
        for index in range(5):
            action("taping", f"step-{index}", {"type": "step", "index": index}, moment)
        action("taping", "send", {"type": "finish-box", "outcome": "good"}, moment)
        action("packing", "packing-shift", {"type": "shift", "operation": "start", "operator": "Paket Operatörü"}, moment)
        with patch("mes_web.employee_stations.now_ms", return_value=moment + 1_000):
            incoming = client.get("/api/employee-stations/packing").json()["items"][0]
            self.assertEqual(incoming["stage"], "transit")
        item = action("packing", "pack", {"type": "pack", "itemId": incoming["id"]}, moment + 4_000)["items"][0]
        self.assertEqual(item["stage"], "packed")
        self.assertEqual(item["packedBy"], "Paket Operatörü")
        self.assertEqual(manager.read_state()["counts"]["total"], 0)
        self.assertEqual(runtime.mqtt_client.published, [])

    def test_live_box_uses_shared_cutting_and_only_packs_after_verified_line_exit(self):
        client, _, manager, _, runtime = self.build()
        manager.apply_control("shift_start")
        key = client.get("/api/manual-coating").json()["progress"]["order_key"]
        body = {"operator": "Giyotin operatörü", "order_id": "IE-10", "order_key": key, "quantity": 2, "request_id": "cut"}
        self.assertEqual(client.post("/api/cutting-workflow", json=body).status_code, 200)
        for workspace, name in (("taping", "Bant Operatörü"), ("packing", "Paket Operatörü")):
            response = self.post(client, workspace, workspace, {"type": "shift", "operation": "start", "operator": name})
            self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.post(client, "taping", "start", {"type": "start-box", "color": "blue"}).status_code, 200)
        for index in range(5):
            self.assertEqual(self.post(client, "taping", f"step-{index}", {"type": "step", "index": index}).status_code, 200)
        finish = self.post(client, "taping", "send", {"type": "finish-box", "outcome": "good"})
        self.assertEqual(finish.status_code, 200, finish.text)
        handed = finish.json()["handoff"]
        self.assertEqual(handed["status"], "waiting_entry")
        self.assertEqual(client.get("/api/manual-coating").json()["progress"]["completed_qty"], 1)
        self.assertEqual(manager.read_state()["counts"]["total"], 0)
        packing = "/api/employee-stations/packing"
        box = client.get(packing).json()["items"][0]
        self.assertEqual(box["stage"], "transit")
        self.assertNotEqual(self.post(client, "packing", "early", {"type": "pack", "itemId": box["id"]}).status_code, 200)
        t1 = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
        manager.apply_mega_log("MEGA|AUTO|QUEUE=ENQ|ITEM_ID=42|MEASURE_ID=7|COLOR=MAVI|TRAVEL_MS=4500|PENDING=1", t1)
        confirmed = self.post(client, "taping", "confirm", {
            "type": "handoff-confirm", "id": handed["id"], "itemId": "42", "measureId": "7",
        })
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertEqual(client.get(packing).json()["items"][0]["stage"], "transit")
        t2 = (datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat()
        manager.apply_mega_log("MEGA|ROBOT|EVENT=RELEASED|ITEM_ID=42|MEASURE_ID=7|TRIGGER=TIMER", t2)
        manager.apply_mega_log("MEGA|AUTO|EVENT=PICKPLACE_DONE|ITEM_ID=42|MEASURE_ID=7|COLOR=MAVI", t2)
        self.assertEqual(client.get(packing).json()["items"][0]["stage"], "exited")
        boxed = self.post(client, "packing", "pack", {"type": "pack", "itemId": box["id"]})
        self.assertEqual(boxed.status_code, 200, boxed.text)
        self.assertEqual(boxed.json()["items"][0]["stage"], "packed")
        self.assertEqual(manager.read_state()["counts"]["total"], 1)
        self.assertEqual(runtime.mqtt_client.published, [])

    def test_lan_station_mode_protects_dashboard_and_observer(self):
        client, config, *_ = self.build(host="192.0.2.20")
        config.employee_tablets_enabled = True
        self.assertEqual(client.get("/bantlama", headers={"host": "192.0.2.10:8080"}).status_code, 200)
        for path in ("/", "/calisan/izle/taping", "/api/employee-observer/taping", "/kiosk-tasarla",
                     "/api/modules/konveyor_main/dashboard"):
            self.assertEqual(client.get(path, headers={"host": "192.0.2.10:8080"}).status_code, 403)

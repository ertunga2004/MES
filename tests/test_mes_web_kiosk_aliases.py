import unittest

import test_mes_web_kiosk_app as kiosk_app


class KioskAliasTests(unittest.TestCase):
    _build_client = kiosk_app.KioskAppTests._build_client
    auth = ("muhendis", "test-kiosk-only")

    def _draft(self, client, slug: str):
        return client.put(f"/api/kiosk-designs/{slug}", auth=self.auth, json={
            "revision": 0,
            "design": {"title": "Boyama", "steps": [{"label": "Yüzeyi kontrol et", "kind": "check"}]},
        })

    def _publish(self, client, slug: str):
        return client.post(f"/api/kiosk-designs/{slug}/publish", auth=self.auth, json={"revision": 1})

    def test_short_url_and_observer_catalog_expose_only_published_kiosks(self) -> None:
        client, _, manager, *_ = self._build_client(kiosk_password="test-kiosk-only")
        manager.import_work_orders([{"orderId": "IE-10", "stockCode": "BOX", "quantity": 10}])
        manager.start_work_order("IE-10")
        self.assertEqual(self._draft(client, "boyama").json()["path"], "/boyama")
        self.assertEqual(self._draft(client, "kalite").status_code, 200)
        self.assertEqual(client.get("/boyama").status_code, 404)
        self.assertEqual(client.get("/calisan/kiosk/boyama").status_code, 404)
        self.assertEqual(client.get("/api/employee-observer/kiosks").json(), [])
        self.assertEqual(self._publish(client, "boyama").status_code, 200)
        for url in ("/boyama", "/istasyon/boyama"):
            response = client.get(url)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.headers["content-security-policy"], "frame-ancestors 'none'")
        observer = client.get("/calisan/kiosk/boyama")
        self.assertEqual(observer.status_code, 200, observer.text)
        self.assertEqual(observer.headers["content-security-policy"], "frame-ancestors 'self'")
        self.assertEqual(client.get("/api/employee-observer/kiosks").json(),
                         [{"slug": "boyama", "title": "Boyama", "path": "/calisan/kiosk/boyama"}])

        operator_api = "/api/station-kiosks/boyama"
        order = client.get(operator_api).json()["order"]
        started = client.post(f"{operator_api}/start", json={
            "order_id": order["id"], "order_key": order["key"], "version": 1,
            "operator": "Deneme Operatörü", "run_id": "test-run",
        })
        self.assertEqual(started.status_code, 200, started.text)
        observer_api = "/api/employee-observer/kiosks/boyama"
        board = client.get(observer_api).json()
        self.assertEqual(board["active"]["operator"], "Deneme Operatörü")
        self.assertNotIn("run_id", board["active"])
        self.assertNotIn("key", board["order"])
        self.assertEqual(client.post(observer_api, json={}).status_code, 405)
        self.assertEqual(manager.read_state()["stationKiosks"]["boyama"]["active"]["run_id"], "test-run")

    def test_reserved_aliases_do_not_shadow_fixed_routes_and_legacy_kiosk_survives(self) -> None:
        client, _, manager, *_ = self._build_client(kiosk_password="test-kiosk-only")
        self.assertEqual(self._draft(client, "boyama").status_code, 200)
        self.assertEqual(self._publish(client, "boyama").status_code, 200)
        for slug in ("bantlama", "paketleme", "tekniker", "teknisyen", "muhendis", "mühendis", "calisan", "kaplama", "giyotin", "health", "static"):
            with self.subTest(slug=slug):
                self.assertEqual(self._draft(client, slug).status_code, 422)
        state = manager.read_state()
        state["stationKiosks"]["health"] = state["stationKiosks"].pop("boyama")
        manager.write_state(state)
        self.assertEqual(client.get("/health").json()["status"], "ok")
        self.assertEqual(client.get("/istasyon/health").status_code, 200)
        designs = client.get("/api/kiosk-designs", auth=self.auth).json()
        self.assertEqual(designs[0]["path"], "/istasyon/health")

    def test_remote_access_cannot_open_kiosk_observation_or_alias(self) -> None:
        client, *_ = self._build_client(host="192.0.2.20")
        for path in ("/boyama", "/calisan/kiosk/boyama", "/api/employee-observer/kiosks", "/api/employee-observer/kiosks/boyama"):
            with self.subTest(path=path):
                self.assertEqual(client.get(path).status_code, 403)

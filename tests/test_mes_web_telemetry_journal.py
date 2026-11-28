import csv
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from mes_web import app as app_module
from mes_web.config import AppConfig
from mes_web.mqtt_runtime import MqttIngestClient
from mes_web.plant_projection import runtime_projection
from mes_web.store import DashboardStore
from mes_web.telemetry_journal import LOCAL_TIME, TelemetryJournal


class TelemetryJournalTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        env = patch.dict(os.environ, {'MES_WEB_OEE_RUNTIME_STATE_PATH': str(Path(folder.name) / 'runtime.json'),
                                     'MES_WEB_WORKSPACE_ACCESS_ENABLED': '0', 'MES_WEB_VISION_INGEST_ENABLED': '1'})
        env.start()
        self.addCleanup(env.stop)
        self.config = AppConfig.from_env()
        self.store = DashboardStore(self.config)
        self.module = self.config.module_id
        globals_patch = patch.multiple(app_module, config=self.config, store=self.store)
        globals_patch.start()
        self.addCleanup(globals_patch.stop)
        self.client = TestClient(app_module.create_app(), client=('127.0.0.1', 50000))
        self.addCleanup(self.client.close)
        self.camera = f'/api/modules/{self.module}/camera-records'

    def test_mqtt_observations_are_persisted_deduplicated_and_exportable(self):
        ingest = MqttIngestClient(self.config, self.store)
        now = datetime.now(LOCAL_TIME).replace(hour=9, minute=22, second=20, microsecond=0)
        reading = {'device_name': 'Gözlemci', 'event': 'line_crossed', 'track_id': 3, 'frame_index': 450,
                   'observed_at': now.isoformat(), 'color_name': 'red', 'product_code': 'KUTU-10', 'confidence': 0.96}
        failed = {'device_name': 'Gözlemci', 'event': 'read_failed', 'event_id': 'fail-2',
                  'observed_at': (now + timedelta(seconds=20)).isoformat(), 'barcode': '=1+2', 'error': 'Kod okunamadı'}
        for payload in (reading, reading, {**reading, 'event': 'box_confirmed'}, failed):
            message = SimpleNamespace(topic=self.config.topics['vision_events'], payload=json.dumps(payload, ensure_ascii=False).encode())
            ingest._on_message(None, None, message)

        page = self.client.get(self.camera, params={'limit': 1}).json()
        self.assertEqual((page['count'], page['today'], page['items'][0]['result']), (2, {'failed': 1, 'success': 1}, 'failed'))
        detail = self.client.get(f"{self.camera}/{page['items'][0]['id']}").json()
        self.assertEqual(json.loads(detail['raw']), failed)
        self.assertIsNone(detail['image_url'])
        persisted = TelemetryJournal(self.config.telemetry_journal_path)
        filtered = persisted.camera_page({'product': 'kutu-10', 'date_from': now.date().isoformat(), 'time_to': '09:22'},
                                         page=1, limit=25, today=now.date().isoformat())
        self.assertEqual(filtered['count'], 1)
        self.assertEqual(filtered['items'][0]['result'], 'success')
        self.assertEqual(self.client.get(self.camera, params={'date_from': 'bad-date'}).status_code, 422)
        export = self.client.get(f'{self.camera}/export', params={'result': 'failed'})
        self.assertEqual(export.status_code, 200)
        entries = list(csv.reader(io.StringIO(export.content.decode('utf-8-sig')), delimiter=';'))
        self.assertEqual((len(entries), entries[1][5], entries[1][12]), (2, "'=1+2", 'Kod okunamadı'))

    def test_system_connection_events_record_loss_and_recovery_once(self):
        now = datetime(2026, 11, 27, 13, tzinfo=timezone.utc)
        self.store.set_mqtt_connection(True, received_at=now.isoformat())
        self.store.apply_heartbeat(self.module, received_at=now.isoformat())
        self.store.observe_equipment(self.module, now)
        disconnected = now + timedelta(seconds=self.config.heartbeat_timeout_sec + 1)
        self.store.observe_equipment(self.module, disconnected)
        self.store.observe_equipment(self.module, disconnected)
        self.store.apply_heartbeat(self.module, received_at=disconnected.isoformat())
        self.store.observe_equipment(self.module, disconnected)
        payload = self.client.get(f'/api/modules/{self.module}/system-status').json()
        self.assertEqual(payload['database'], 'online')
        records = [row for row in reversed(payload['events']) if row['device'] == 'Arduino Mega']
        self.assertEqual([row['level'] for row in records], ['info', 'error', 'info'])

    def test_only_verified_camera_items_link_to_matching_production_window(self):
        observed = datetime(2026, 11, 27, 13, 30, tzinfo=timezone.utc)
        wire = {'event': 'line_crossed', 'color_name': 'yellow', 'track_id': 4, 'timestamp': observed.isoformat()}
        linked = {'item_id': '4', 'measure_id': '8', 'correlation_status': 'MATCHED'}
        self.store.apply_vision_event(self.module, {**wire, **linked}, received_at=observed.isoformat(), wire=wire)
        other = {**wire, 'track_id': 5}
        self.store.apply_vision_event(self.module, {**other, **linked, 'correlation_status': 'AMBIGUOUS'},
                                      received_at=observed.isoformat(), wire=other)
        journal = self.store.journal
        journal.link_camera('4', '8', 'OLD-WO', 'SCRAP', (observed - timedelta(days=2)).isoformat(),
                            (observed - timedelta(days=1)).isoformat())
        journal.link_camera('4', '8', 'WO-A', 'GOOD', (observed - timedelta(seconds=5)).isoformat(),
                            (observed + timedelta(seconds=5)).isoformat())
        page = journal.camera_page({}, page=1, limit=25, today=observed.date().isoformat())
        records = {row['track_id']: row for row in page['items']}
        self.assertEqual((records['4']['order_id'], records['4']['quality']), ('WO-A', 'GOOD'))
        self.assertEqual((records['5']['item_id'], records['5']['order_id']), ('', ''))

    def test_production_projection_uses_only_dated_records_and_observed_cycles(self):
        now = datetime(2026, 11, 27, 9, tzinfo=LOCAL_TIME)
        items = {}
        for number in range(4):
            completed = now - timedelta(seconds=15 * number + 1)
            items[str(number)] = {'item_id': str(number), 'work_order_id': 'WO-A', 'completed_at': completed.isoformat(),
                                  'picked_at': (completed - timedelta(seconds=4)).isoformat()}
        items['yesterday'] = {'completed_at': (now - timedelta(days=1)).isoformat()}
        items['pending'] = {'item_id': 'pending', 'picked_at': now.isoformat()}
        result = runtime_projection({'itemsById': items, 'queueOrder': ['pending'], 'workOrders': {'activeOrderId': 'WO-A'}}, now)
        self.assertEqual((result['daily_completed'], result['cycle_median_ms'], result['rate_ms']), (4, 4000, 15000))
        self.assertEqual((result['queue_item'], result['robot_item']), ('pending', 'pending'))

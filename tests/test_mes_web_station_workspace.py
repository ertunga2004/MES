import json
import os
from pathlib import Path
import secrets
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from mes_web import app as app_module
from mes_web.config import AppConfig
from mes_web.excel_runtime import ExcelRuntimeSink
from mes_web.mqtt_runtime import MqttIngestClient
from mes_web.oee_state import OeeRuntimeStateManager
from mes_web.station_access import STATION_PORTS
from mes_web.station_workflow import TAPING_STEPS


class StationWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.passwords = {user: secrets.token_urlsafe(24) for user in ('admin', 'muhendis', 'sef')}
        env = patch.dict(os.environ, {
            'MES_WEB_WORKSPACE_ACCESS_ENABLED': '1',
            'MES_WEB_WORKSPACE_ADMIN_PASSWORD': self.passwords['admin'],
            'MES_WEB_KIOSK_DESIGN_PASSWORD': self.passwords['muhendis'],
            'MES_WEB_WORKSPACE_SUPERVISOR_PASSWORD': self.passwords['sef'],
            'MES_WEB_WORKSPACE_STATE_PATH': str(Path(self.folder.name) / 'stations.sqlite'),
            'MES_WEB_WORKSPACE_SESSION_SECRET': secrets.token_urlsafe(32),
        })
        env.start()
        self.addCleanup(env.stop)
        config = patch.object(app_module, 'config', AppConfig.from_env())
        config.start()
        self.addCleanup(config.stop)
        self.app = app_module.create_app()
        self.admin = self.actor('admin')

    def client(self, address='192.0.2.10'):
        client = TestClient(self.app, base_url='https://mes.example', client=(address, 50000))
        self.addCleanup(client.close)
        return client

    def actor(self, user):
        client = self.client()
        response = client.post('/api/workspace/login', json={'username': user, 'password': self.passwords[user]})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn('HttpOnly', response.headers['set-cookie'])
        self.assertIn('Secure', response.headers['set-cookie'])
        return client

    def pair(self, station):
        code = self.admin.post(f'/api/workspace/pair-codes/{station}', json={}).json()['code']
        client = self.client()
        result = client.post('/api/workspace/pair', json={'code': code})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['bound_station_id'], station)
        self.assertEqual(self.client().post('/api/workspace/pair', json={'code': code}).status_code, 400)
        return client, result.json()['path']

    def action(self, client, station, action, expected=200, **fields):
        response = client.post(f'/api/workspace/tablet/{station}/actions', json={'action': action, 'fields': fields})
        self.assertEqual(response.status_code, expected, response.text)
        return response.json()

    def test_erp_cut_and_taping_tablets_share_the_order_and_excel_trace(self):
        folder = Path(self.folder.name)
        workbook_path = folder / 'tablets.xlsx'
        with patch.dict(os.environ, {'MES_WEB_EXCEL_WORKBOOK_PATH': str(workbook_path)}):
            sink = ExcelRuntimeSink(AppConfig(excel_flush_interval_sec=0.01))
            sink.start()
            self.addCleanup(sink.stop)
            manager = OeeRuntimeStateManager(folder / 'production.json')
            manager.import_work_orders([{
                'order_id': 'TABLET-1', 'quantity': 1, 'product_color': 'blue', 'unit': 'adet',
                'station_orders': [
                    {'station_code': 'giyotin', 'station_order_id': 'KES-1', 'target_qty': 2, 'unit': 'adet'},
                    {'station_code': 'bantlama', 'station_order_id': 'BNT-1', 'target_qty': 1, 'unit': 'adet'},
                ],
            }])
            manager.start_work_order('TABLET-1')
            service = SimpleNamespace(excel_sink=sink)
            with patch.object(app_module, 'oee_state_manager', manager), patch.object(app_module, 'runtime_service', service):
                self.app = app_module.create_app()
                self.admin = self.actor('admin')
                giyotin, _ = self.pair('giyotin')
                bantlama, _ = self.pair('bantlama')
                cut_board = self.action(giyotin, 'giyotin', 'shift-start', operator='Kesim')['board']
                tape_board = self.action(bantlama, 'bantlama', 'shift-start', operator='Bantlama')['board']
                key = cut_board['erpOrder']['key']
                self.assertEqual(cut_board['erpOrder']['stationOrderId'], 'KES-1')
                self.assertEqual(tape_board['erpOrder']['stationOrderId'], 'BNT-1')
                self.assertEqual(cut_board['cut']['blue'], 0)
                start = dict(orderKey=key, color='blue', box='KUTU-1')
                cut = dict(orderKey=key, orderId='TABLET-1', color='blue', count=1, length=100,
                           lot='BANT-1', result='good', shield=True)
                self.action(giyotin, 'giyotin', 'cut', **cut, requestId='cut-1')
                self.action(giyotin, 'giyotin', 'cut', **cut, requestId='cut-1')
                self.action(bantlama, 'bantlama', 'start', 409, **start)
                self.action(giyotin, 'giyotin', 'cut', **cut, requestId='cut-2')
                board = bantlama.get('/api/workspace/tablet/bantlama').json()
                self.assertEqual(board['cut']['blue'], 2)
                self.action(bantlama, 'bantlama', 'start', **start)
                box = dict(orderKey=key, activeBoxId='KUTU-1')
                self.action(bantlama, 'bantlama', 'finish', 409, **box, outcome='good', length=100)
                for index in range(len(TAPING_STEPS)):
                    self.action(bantlama, 'bantlama', 'step', **box, index=index, checked=True)
                board = self.action(bantlama, 'bantlama', 'finish', **box, outcome='good', length=100)['board']
                self.assertEqual([(row['id'], row['stage']) for row in board['boxes']], [('KUTU-1', 'handoff')])
                self.action(bantlama, 'bantlama', 'finish', 409, **box, outcome='good', length=100)
            sink.stop()
        workbook = load_workbook(workbook_path, read_only=True)
        try:
            headers, *values = workbook['1_Olay_Logu'].values
            rows = [dict(zip(headers, row)) for row in values if row[headers.index('event_uid')]]
            self.assertEqual([(row['station_order_id'], row['station_code'], row['quantity']) for row in rows],
                             [('KES-1', 'giyotin', 1), ('KES-1', 'giyotin', 1), ('BNT-1', 'bantlama', 1)])
            self.assertEqual(rows[-1]['item_id'], 'KUTU-1')
        finally:
            workbook.close()

    def test_routed_box_waits_for_exact_release_and_closes_once_in_excel_and_ferp(self):
        folder = Path(self.folder.name)
        workbook_path = folder / 'flow.xlsx'
        pending = folder / 'ferp-pending'
        self.enterContext(patch.dict(os.environ, {'MES_WEB_EXCEL_WORKBOOK_PATH': str(workbook_path),
                                                  'MES_WEB_FERP_EXPORT_PENDING_DIR': str(pending)}))
        config = AppConfig.from_env()
        manager = OeeRuntimeStateManager(folder / 'flow.json')
        order_id, box_id = 'PILOT-1', 'KUTU-PILOT-1'
        stations = ('giyotin', 'bantlama', 'konveyor', 'paketleme')
        route = [dict(station_code=station, station_order_id=f'PILOT-1-{station.upper()}',
                      target_qty=2 if station == 'giyotin' else 1, unit='adet') for station in stations]
        manager.import_work_orders([dict(order_id=order_id, quantity=1, product_color='blue', unit='adet', station_orders=route)])
        manager.start_work_order(order_id)
        sink = ExcelRuntimeSink(config)
        sink.start()
        self.addCleanup(sink.stop)
        service = SimpleNamespace(excel_sink=sink)
        store = self.enterContext(patch.object(app_module, 'store'))
        mqtt = MqttIngestClient(config, store, excel_sink=sink, oee_state_manager=manager)

        def mega(payload, *, retain=False):
            mqtt._on_message(None, None, SimpleNamespace(topic=config.topics['logs'], payload=payload, retain=retain))

        def measurement(item, measure, color):
            return f'MEGA|TCS3200|STATE=MEASURING|ITEM_ID={item}|MEASURE_ID={measure}|FINAL={color}'

        def release(item, measure):
            return f'MEGA|ROBOT|EVENT=RELEASED|ITEM_ID={item}|MEASURE_ID={measure}'

        with (patch.object(app_module, 'oee_state_manager', manager), patch.object(app_module, 'runtime_service', service),
              patch.object(app_module, 'config', config)):
            self.app = app_module.create_app()
            self.admin = self.actor('admin')
            tablets = {station: self.pair(station)[0] for station in stations}

            def board(station):
                response = tablets[station].get(f'/api/workspace/tablet/{station}')
                self.assertEqual(response.status_code, 200, response.text)
                return response.json()

            order_key = board('giyotin')['erpOrder']['key']

            def action(station, name, expected=200, **fields):
                return self.action(tablets[station], station, name, expected, orderKey=order_key, **fields)

            for station in stations:
                self.assertIn(f'data-station="{station}"', tablets[station].get(f'/operations/{station}').text)
                action(station, 'shift-start', operator=station)
            cut = dict(orderId=order_id, color='blue', count=1, length=100, lot='BANT-1', result='good', shield=True)
            action('giyotin', 'cut', requestId='pilot-cut-1', **cut)
            action('bantlama', 'start', 409, box=box_id, color='blue')
            action('giyotin', 'cut', 409, requestId='wrong-color-cut', **{**cut, 'color': 'red'})
            action('giyotin', 'cut', requestId='pilot-cut-2', **cut)
            action('giyotin', 'cut', requestId='pilot-cut-2', **cut)
            action('bantlama', 'start', box=box_id, color='blue')
            for index in range(len(TAPING_STEPS)):
                action('bantlama', 'step', activeBoxId=box_id, index=index, checked=True)
            action('bantlama', 'finish', activeBoxId=box_id, outcome='good', length=100)
            conveyor = board('konveyor')
            self.assertEqual(conveyor['erpOrder']['stationOrderId'], 'PILOT-1-KONVEYOR')
            handed_off, = conveyor['boxes']
            self.assertEqual((handed_off['id'], handed_off['orderId'], handed_off['stage']), (box_id, order_id, 'handoff'))
            self.assertNotIn('exitEvent', handed_off)

            pack_fields = dict(box=box_id, size='S', count=1, label='ETK-1', weight=80, protected=True)
            action('paketleme', 'pack', 409, **pack_fields)
            action('konveyor', 'match', 409, box=box_id, lineItemId='91', measurement='801')
            mega(measurement('91', '801', 'RED'))
            mega(release('91', '801'))
            action('konveyor', 'match', 409, box=box_id, lineItemId='91', measurement='801')
            self.assertEqual(board('paketleme')['boxes'][0]['stage'], 'handoff')
            self.assertEqual(manager.read_state()['workOrders']['ordersById'][order_id]['productionQty'], 0)

            right = measurement('92', '802', 'BLUE')
            mega(right, retain=True)
            action('konveyor', 'match', 409, box=box_id, lineItemId='92', measurement='802')
            mega(right)
            mega('MEGA|AUTO|QUEUE=ENQ|ITEM_ID=92|MEASURE_ID=802|COLOR=BLUE|TRAVEL_MS=50')
            self.assertEqual(board('konveyor')['lineMeasurements'][-1], {'item_id': '92', 'measure_id': '802', 'color': 'blue'})
            match = dict(box=box_id, lineItemId='92', measurement='802')
            action('konveyor', 'match', **match)
            action('konveyor', 'match', **match)
            mega(release('92', '999'))
            mega('MEGA|ROBOT|EVENT=RELEASED|ITEM_ID=92')
            mega('MEGA|AUTO|EVENT=PICKPLACE_DONE|ITEM_ID=92|MEASURE_ID=802')
            action('konveyor', 'exit', 409, box=box_id)
            action('paketleme', 'pack', 409, **pack_fields)
            self.assertEqual(board('paketleme')['boxes'][0]['stage'], 'transit')

            mega(release('92', '802'))
            mega(release('92', '802'))
            ready, = board('paketleme')['boxes']
            self.assertEqual((ready['id'], ready['orderId'], ready['stage']), (box_id, order_id, 'exited'))
            action('paketleme', 'pack', **pack_fields)
            action('paketleme', 'pack', 409, **pack_fields)
            action('paketleme', 'seal', 422)
            self.assertFalse(pending.exists())
            with patch.object(app_module, 'write_packing_closure', side_effect=OSError('test disk failure')):
                action('paketleme', 'seal', 503, confirmed=True)
            self.assertEqual(board('paketleme')['carton']['stage'], 'sealed')
            self.assertEqual(manager.read_state()['workOrders']['ordersById'][order_id]['status'], 'completed')
            action('paketleme', 'seal', confirmed=True)
            action('paketleme', 'seal', confirmed=True)
            mega(right)
            mega(release('92', '802'))
            state = manager.read_state()
            self.assertEqual(state['workOrders']['ordersById'][order_id]['productionQty'], 1)
            self.assertEqual(len(state['workOrders']['completionLog']), 1)
            self.assertEqual(state['workOrders']['inventoryByProduct'], {})
            self.assertEqual(state['itemsById']['92']['work_order_id'], order_id)

        export_path, = pending.glob('*.json')
        export = json.loads(export_path.read_text(encoding='utf-8'))
        self.assertEqual(export['schema'], 'ferp_mes_export.v1')
        self.assertEqual(export['work_order']['ferp_labels']['lblMMFB0_NUMBER'], order_id)
        event, = export['station_flow']
        self.assertEqual((event['item_id'], event['station_order_id'], event['measure_id'], event['operator']),
                         (box_id, 'PILOT-1-PAKETLEME', '802', 'paketleme'))

        sink.stop()
        restarted = ExcelRuntimeSink(config)
        restarted.start()
        try:
            restarted.record_work_order_state(state, datetime.now(timezone.utc).isoformat())
        finally:
            restarted.stop()
        workbook = load_workbook(workbook_path, read_only=True)
        try:
            headers, *values = workbook['1_Olay_Logu'].values
            rows = [dict(zip(headers, row)) for row in values if row[headers.index('event_uid')]]
            self.assertEqual(len(rows), 6)
            self.assertEqual(len({row['event_uid'] for row in rows}), 6)
            self.assertEqual({(row['production_order_id'], row['item_id']) for row in rows}, {(order_id, box_id)})
            self.assertCountEqual([row['event_type_code'] for row in rows],
                                  ['manual_cut_recorded', 'manual_cut_recorded', 'taping_completed',
                                   'conveyor_matched', 'conveyor_exit_verified', 'packing_closed'])
            closed, = [row for row in rows if row['event_type_code'] == 'packing_closed']
            self.assertEqual(closed['event_uid'], event['event_uid'])
            self.assertEqual(closed['station_order_id'], event['station_order_id'])
        finally:
            workbook.close()

    def test_station_lock_and_legacy_control_panel_boundary(self):
        anonymous = self.client()
        self.assertEqual(anonymous.get('/', follow_redirects=False).headers['location'], '/mes-oturum')
        self.assertEqual(anonymous.get('/operations/bantlama', follow_redirects=False).headers['location'], '/tablet-eslestir')
        self.assertEqual(anonymous.get('/api/workspace/tablet/bantlama').status_code, 401)
        tablet, address = self.pair('bantlama')
        self.assertEqual(address, '/?module=konveyor_main&tab=operations/bantlama')
        page = tablet.get(address)
        self.assertIn('data-station="bantlama"', page.text)
        self.assertNotIn('href="/"', page.text)
        self.assertEqual(tablet.get('/static/atolye-tablets.mjs').status_code, 200)
        self.assertEqual(tablet.get('/operations/bantlama').status_code, 200)
        for path in ('/', '/?tab=monitoring', '/?tab=operations/giyotin', '/atolye-onizleme',
                     '/api/modules/konveyor_main/dashboard', '/api/workspace/tablet/kaplama', '/mes-oturum'):
            self.assertEqual(tablet.get(path, follow_redirects=False).status_code, 403, path)
        self.action(tablet, 'paketleme', 'shift-start', 403, operator='Test')
        self.action(tablet, 'bantlama', 'start', 409, box='KUTU-TEST', color='blue')

    def test_staff_roles_and_cross_origin_writes(self):
        engineer = self.actor('muhendis')
        supervisor = self.actor('sef')
        for staff in (self.admin, engineer, supervisor):
            self.assertEqual(staff.get('/?module=konveyor_main&tab=monitoring').status_code, 200)
            self.assertEqual(staff.get('/api/workspace/monitoring').status_code, 200)
        self.assertEqual(engineer.get('/designer', follow_redirects=False).headers['location'], '/atolye-onizleme')
        self.assertEqual(engineer.get('/atolye-onizleme').status_code, 200)
        self.assertEqual(supervisor.get('/atolye-onizleme').status_code, 403)
        self.assertEqual(supervisor.get('/api/workspace/templates').status_code, 403)
        self.assertEqual(engineer.post('/api/workspace/pair-codes/giyotin', json={}).status_code, 403)
        self.action(supervisor, 'bantlama', 'shift-start', 403, operator='Test')
        rejected = self.admin.post('/api/workspace/pair-codes/bantlama', json={}, headers={'Origin': 'https://other.example'})
        self.assertEqual(rejected.status_code, 403)

    def test_station_ports_open_only_their_assigned_station(self):
        root = self.admin.get('/')
        self.assertNotIn('tablet-workspace-link', root.text)
        for station, port in STATION_PORTS.items():
            address = f'https://mes.example:{port}'
            view = self.admin.get(address + '/', follow_redirects=False)
            self.assertEqual(view.status_code, 200, address)
            self.assertIn(f'data-station="{station}"', view.text)
            self.assertEqual(self.admin.get(address + '/?tab=monitoring').status_code, 403)
            self.assertEqual(self.admin.get(address + '/atolye-onizleme').status_code, 403)
            self.assertNotIn('href="/"', view.text)

        bantlama = 'https://mes.example:18781'
        paketleme = 'https://mes.example:18782'
        spoofed = self.admin.get(paketleme + '/', headers={'Host': 'mes.example:18781'})
        self.assertIn('data-station="paketleme"', spoofed.text)
        self.assertEqual(self.admin.get(paketleme + '/?tab=operations/bantlama').status_code, 403)
        self.assertEqual(self.admin.get(paketleme + '/api/workspace/tablet/bantlama').status_code, 403)

        tablet = self.client()
        self.assertEqual(tablet.get(bantlama + '/', follow_redirects=False).headers['location'], '/tablet-eslestir')
        invitation = self.admin.post('/api/workspace/pair-codes/bantlama', json={}).json()
        self.assertEqual(invitation['station_port'], 18781)
        self.assertEqual(tablet.post(paketleme + '/api/workspace/pair', json={'code': invitation['code']}).status_code, 403)
        paired = tablet.post(bantlama + '/api/workspace/pair', json={'code': invitation['code']})
        self.assertEqual(paired.status_code, 200, paired.text)
        self.assertEqual(paired.json()['path'], '/')
        self.assertIn('data-station="bantlama"', tablet.get(bantlama + '/').text)
        self.assertEqual(tablet.get(paketleme + '/').status_code, 403)
        self.assertEqual(tablet.get('/').status_code, 403)
        action = tablet.post(bantlama + '/api/workspace/tablet/bantlama/actions', json={
            'action': 'shift-start', 'fields': {'operator': 'Örnek Operatör'},
        })
        self.assertEqual(action.status_code, 200, action.text)
        snapshot = self.admin.get('/api/workspace/monitoring').json()
        self.assertEqual(snapshot['stations']['bantlama']['shift']['operator'], 'Örnek Operatör')

    def test_sample_chain_and_observer_uses_other_browser_updates(self):
        giyotin, _ = self.pair('giyotin')
        bantlama, _ = self.pair('bantlama')
        konveyor, _ = self.pair('konveyor')
        paketleme, _ = self.pair('paketleme')
        for tablet, station in ((giyotin, 'giyotin'), (bantlama, 'bantlama'), (konveyor, 'konveyor'), (paketleme, 'paketleme')):
            self.action(tablet, station, 'shift-start', operator='Örnek Operatör')
        self.action(giyotin, 'giyotin', 'cut', 422, color='blue', count=2, lot='KESIM-TEST', length=100, result='good')
        self.action(giyotin, 'giyotin', 'cut', color='blue', count=2, lot='KESIM-TEST', length=100, result='good', shield=True)
        self.action(bantlama, 'bantlama', 'start', box='KUTU-TEST', color='blue')
        self.action(bantlama, 'bantlama', 'shift-end', 409)
        self.action(bantlama, 'bantlama', 'finish', 409, activeBoxId='KUTU-TEST', outcome='good', length=100)
        for index in range(4):
            self.action(bantlama, 'bantlama', 'step', activeBoxId='KUTU-TEST', index=index, checked=True)
        self.action(bantlama, 'bantlama', 'finish', activeBoxId='KUTU-TEST', outcome='good', length=100)
        self.action(bantlama, 'bantlama', 'help', description='Örnek kontrol')
        self.action(bantlama, 'bantlama', 'shift-end')
        self.action(konveyor, 'konveyor', 'match', box='KUTU-TEST', measurement='OLC-TEST')
        fields = dict(box='KUTU-TEST', size='M', label='ETK-TEST', weight=120, count=1, protected=True)
        self.action(paketleme, 'paketleme', 'pack', 409, **fields)
        self.action(konveyor, 'konveyor', 'exit', box='KUTU-TEST')
        self.action(paketleme, 'paketleme', 'pack', **fields)
        monitor = self.actor('sef').get('/api/workspace/monitoring').json()
        self.assertEqual(len(monitor['stations']), 8)
        self.assertEqual(monitor['stations']['paketleme']['packed']['blue'], 11)
        self.assertEqual(monitor['stations']['tekniker']['faults'][0]['kind'], 'help')
        self.assertIsNone(monitor['stations']['bantlama']['shift'])

    def test_template_publication_is_shared_and_persists_across_apps(self):
        engineer = self.actor('muhendis')
        template = {'title': 'Kaplama deneme listesi', 'cards': [{'kind': 'steps'}],
                    'steps': [{'label': 'Örnek kontrol', 'kind': 'check', 'required': True}]}
        draft = engineer.put('/api/workspace/templates/kaplama', json={'revision': 0, 'design': template})
        self.assertEqual(draft.status_code, 200, draft.text)
        self.assertEqual(engineer.put('/api/workspace/templates/kaplama', json={'revision': 0, 'design': template}).status_code, 409)
        tablet, _ = self.pair('kaplama')
        self.assertIsNone(tablet.get('/api/workspace/tablet/kaplama').json()['template'])
        published = engineer.post('/api/workspace/templates/kaplama/publish', json={'revision': 1})
        self.assertEqual(published.status_code, 200, published.text)
        self.action(tablet, 'kaplama', 'shift-start', operator='Örnek Operatör')
        self.action(tablet, 'kaplama', 'template-record', 422, version='1')
        self.action(tablet, 'kaplama', 'template-record', version='1', **{'step-0':'on'})
        self.action(tablet, 'kaplama', 'coat', batch='KPL-TEST', tank='T-01', chemical='LOT-TEST', concentration=1,
                    thickness=2, drying=3, quantity=2, outcome='good')
        self.app = app_module.create_app()
        copy = self.actor('sef').get('/api/workspace/monitoring').json()['stations']['kaplama']
        self.assertEqual(copy['template']['design']['title'], 'Kaplama deneme listesi')
        self.assertEqual(copy['templateRecord']['values'], [True])
        self.assertEqual(copy['coating']['total'], 14)

    def test_technician_quality_and_material_actions(self):
        technician, _ = self.pair('tekniker')
        quality, _ = self.pair('kalite')
        material, _ = self.pair('malzeme')
        for tablet, station in ((technician, 'tekniker'), (quality, 'kalite'), (material, 'malzeme')):
            self.action(tablet, station, 'shift-start', operator='Örnek Operatör')
        self.action(technician, 'tekniker', 'accept', fault='ARZ-014')
        self.action(technician, 'tekniker', 'reply', fault='ARZ-014', reply='Örnek inceleme')
        repair = dict(fault='ARZ-014', category='Örnek', parts='Stokta', intervention='Örnek işlem', downtime=5, outcome='repaired')
        self.action(technician, 'tekniker', 'resolve', 422, **repair)
        result = self.action(technician, 'tekniker', 'resolve', tested=True, **repair)
        self.assertEqual(result['board']['faults'][0]['status'], 'resolved')
        result = self.action(quality, 'kalite', 'classify', box='KUTU-785', outcome='allowed', instrument='Örnek ölçer',
                             measured=5, tolerance='Örnek tolerans', visual='good', reason='Örnek karar')
        self.assertEqual(result['board']['qualityLog'][0]['outcome'], 'allowed')
        self.action(material, 'malzeme', 'dispatch', 409, barcode='BAR-TEST', location='Örnek raf', color='blue', quantity=100, condition=True)
        result = self.action(material, 'malzeme', 'dispatch', barcode='BAR-TEST', location='Örnek raf', color='blue', quantity=2, condition=True)
        self.assertEqual(result['board']['materials']['blue'], 10)
        self.assertEqual(result['board']['dispatches'][0]['barcode'], 'BAR-TEST')


if __name__ == '__main__':
    unittest.main()

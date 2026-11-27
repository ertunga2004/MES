import json
import os
from pathlib import Path
import secrets
import tempfile
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from mes_web import app as app_module
from mes_web.anylogic_runner import AnyLogicRunner
from mes_web.config import AppConfig
from mes_web.station_access import STATION_PORTS


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

    def test_anylogic_routes_keep_simulation_controls_in_staff_workspace(self):
        url = '/api/workspace/anylogic'
        supervisor = self.actor('sef')
        tablet, _ = self.pair('bantlama')
        self.assertEqual(tablet.get(url).status_code, 403)
        self.assertEqual(tablet.get(f'{url}/frame').status_code, 403)
        self.assertEqual(self.client().get(f'{url}/frame').status_code, 401)
        frame_response = supervisor.get(f'{url}/frame')
        self.assertEqual(frame_response.status_code, 200)
        self.assertEqual(frame_response.headers['cache-control'], 'no-store')
        self.assertIsNone(frame_response.json()['frame'])
        self.assertFalse(supervisor.get(url).json()['can_control'])
        self.assertEqual(supervisor.post(f'{url}/command', json={'action': 'start'}).status_code, 403)
        self.assertEqual(supervisor.post(f'{url}/command', json={'action': 'speed', 'speed': 5}).status_code, 403)
        self.assertEqual(self.admin.post(f'{url}/command', json={'action': 'start', 'scenario': 'T15'}).status_code, 422)
        self.assertEqual(self.admin.post(f'{url}/command', json={'action': 'start', 'speed': 3}).status_code, 422)
        self.assertEqual(self.admin.post(f'{url}/command', json={'action': 'speed'}).status_code, 422)
        self.assertEqual(self.admin.post(f'{url}/command', json={'action': 'speed', 'speed': 10}).status_code, 409)
        foreign = self.admin.post(f'{url}/command', json={'action': 'start'}, headers={'Origin': 'https://other.example'})
        self.assertEqual(foreign.status_code, 403)

    def test_anylogic_frame_uses_active_engine_run_and_never_replays_a_retired_run(self):
        folder = Path(self.folder.name)
        runner = AnyLogicRunner(folder, folder / 'runtime.json')
        runner.process = SimpleNamespace(poll=lambda: None)
        runner.active = {'id': 'app-run'}
        runner.engine_run_id = 'current-engine-run'
        runner.engine_state = 'paused'
        runner.engine_speed = 5
        live = runner.runs / 'app-run' / 'live'
        live.mkdir(parents=True)
        frame = {'schemaVersion': 1, 'type': 'anylogic-state', 'runId': 'old-engine-run', 'seq': 4, 'simTime': 2}
        path = live / 'live-state.json'
        path.write_text(json.dumps(frame), encoding='utf-8')
        self.assertIsNone(runner.frame()['frame'])
        frame['runId'] = runner.engine_run_id
        path.write_text(json.dumps(frame), encoding='utf-8')
        self.assertEqual(runner.frame(), {'run': runner.active, 'state': 'paused', 'speed': 5, 'frame': {'seq': 4, 'simTime': 2}})
        self.assertEqual(runner._snapshot({'state': 'paused', 'modelTime': 3})['modelTime'], 2)
        path.write_text('{', encoding='utf-8')
        self.assertEqual(runner.frame()['frame']['seq'], 4)
        runner.engine_run_id = 'new-engine-run'
        self.assertIsNone(runner.frame()['frame'])
        runner.process = None
        self.assertIsNone(runner.frame()['frame'])

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
        kalite, _ = self.pair('kalite')
        for tablet, station in ((giyotin, 'giyotin'), (bantlama, 'bantlama'), (konveyor, 'konveyor'),
                                (paketleme, 'paketleme'), (kalite, 'kalite')):
            self.action(tablet, station, 'shift-start', operator='Örnek Operatör')
        cut = dict(color='blue', count=2, lot='KESIM-TEST', length=100, result='good',
                   orderId='WO-2026-0456', requestId='sample-chain-cut')
        self.action(giyotin, 'giyotin', 'cut', 422, **cut)
        self.action(giyotin, 'giyotin', 'cut', **cut, shield=True)
        self.action(bantlama, 'bantlama', 'start', box='KUTU-TEST', color='blue')
        self.action(bantlama, 'bantlama', 'shift-end', 409)
        self.action(bantlama, 'bantlama', 'finish', 409, activeBoxId='KUTU-TEST', outcome='good')
        self.action(bantlama, 'bantlama', 'step', 409, activeBoxId='KUTU-TEST', index=1, checked=True)
        self.action(bantlama, 'bantlama', 'step', 422, activeBoxId='KUTU-TEST', index=0, checked=False)
        for index in range(5):
            board = self.action(bantlama, 'bantlama', 'step', activeBoxId='KUTU-TEST', index=index, checked=True)['board']
            self.assertEqual(board['activeBox']['steps'], [True] * (index + 1) + [False] * (4 - index))
            if index == 3:
                self.action(bantlama, 'bantlama', 'finish', 409, activeBoxId='KUTU-TEST', outcome='good')
        reloaded = bantlama.get('/api/workspace/tablet/bantlama').json()
        self.assertEqual(reloaded['activeBox']['steps'], [True] * 5)
        board = self.action(bantlama, 'bantlama', 'finish', activeBoxId='KUTU-TEST', outcome='good')['board']
        finished = next(box for box in board['boxes'] if box['id'] == 'KUTU-TEST')
        self.assertEqual(finished['stage'], 'handoff')
        self.assertIsNone(finished['length'])
        self.action(bantlama, 'bantlama', 'help', description='Örnek kontrol')
        self.action(bantlama, 'bantlama', 'shift-end')
        self.action(konveyor, 'konveyor', 'match', box='KUTU-TEST', measurement='OLC-TEST')
        fields = dict(box='KUTU-TEST', size='M', label='ETK-TEST', weight=120, count=1, protected=True)
        self.action(paketleme, 'paketleme', 'pack', 409, **fields)
        self.action(konveyor, 'konveyor', 'exit', box='KUTU-TEST')
        review = dict(box='KUTU-TEST', instrument='Ölçüm', measured=12, tolerance='1', visual='good', reason='Tekrar kontrol')
        self.action(kalite, 'kalite', 'classify', outcome='scrap', **review)
        dashboard_path = '/api/workspace/monitoring/dashboard'
        after_review = self.admin.get(dashboard_path).json()['stations']['bantlama']
        self.assertEqual((after_review['total'], after_review['quality']['scrap']), (1, 1))
        self.action(kalite, 'kalite', 'classify', outcome='good', **review)
        self.action(paketleme, 'paketleme', 'pack', **fields)
        monitor = self.actor('sef').get('/api/workspace/monitoring').json()
        self.assertEqual(len(monitor['stations']), 8)
        self.assertEqual(monitor['stations']['paketleme']['packed']['blue'], 11)
        self.assertEqual(monitor['stations']['tekniker']['faults'][0]['kind'], 'help')
        self.assertIsNone(monitor['stations']['bantlama']['shift'])
        self.assertEqual(bantlama.get(dashboard_path).status_code, 403)
        self.assertEqual(self.client().get(dashboard_path).status_code, 401)
        daily = self.actor('sef').get(dashboard_path).json()['stations']
        self.assertEqual(set(daily), {'bantlama', 'paketleme', 'giyotin', 'tekniker'})
        self.assertEqual(daily['bantlama']['total'], 1)
        self.assertEqual(daily['bantlama']['quality']['good'], 1)
        self.assertEqual(daily['paketleme']['total'], 1)
        self.assertEqual(daily['giyotin']['total'], 2)
        self.assertEqual(daily['giyotin']['workers'][0]['count'], 2)
        self.assertIsNone(daily['paketleme']['work']['activeMs'])
        self.assertNotIn('Örnek Operatör', {row['operator'] for row in daily['tekniker']['workers']})

    def test_monitoring_clips_day_and_excludes_overlapping_downtime_from_work(self):
        supervisor = self.actor('sef')
        bantlama, _ = self.pair('bantlama')
        technician, _ = self.pair('tekniker')
        url = '/api/workspace/monitoring/dashboard'
        midnight = datetime(2026, 11, 26, 21, tzinfo=timezone.utc).timestamp()
        minute = -10

        def clock():
            return midnight + minute * 60

        def board():
            return supervisor.get(url).json()['stations']

        with patch('mes_web.station_workflow.time', SimpleNamespace(time=clock)), patch('mes_web.station_monitoring.time', clock):
            self.action(bantlama, 'bantlama', 'shift-start', operator='Bantlama Operatörü')
            self.assertEqual(board()['bantlama']['status'], 'idle')
            box = 'KUTU-IZLEME'
            self.action(bantlama, 'bantlama', 'start', box=box, color='blue')
            minute = 5
            self.assertEqual(board()['bantlama']['status'], 'running')
            self.assertEqual(board()['bantlama']['work']['activeMs'], 300_000)
            self.action(bantlama, 'bantlama', 'pause', activeBoxId=box, reason='Besleme bekliyor')
            self.assertEqual(board()['bantlama']['status'], 'paused')
            self.action(bantlama, 'bantlama', 'fault', description='Merdane kontrolü')

            minute = 7
            self.action(technician, 'tekniker', 'shift-start', operator='Bakım Teknikeri')
            issue = self.admin.get('/api/workspace/monitoring').json()['faults'][0]['id']
            self.action(technician, 'tekniker', 'accept', fault=issue)
            self.assertEqual(board()['bantlama']['status'], 'maintenance')
            self.assertEqual(board()['tekniker']['status'], 'running')
            minute = 10
            self.action(bantlama, 'bantlama', 'resume', activeBoxId=box)
            minute = 12
            self.action(technician, 'tekniker', 'resolve', fault=issue, category='Merdane', parts='Yok',
                        intervention='Kontrol edildi', downtime=5, outcome='repaired', tested=True)
            self.assertEqual(board()['bantlama']['status'], 'running')
            minute = 15
            self.action(bantlama, 'bantlama', 'finish', activeBoxId=box, outcome='rework', reason='Kontrol gerekli')
            self.action(bantlama, 'bantlama', 'finish', 409, activeBoxId=box, outcome='rework', reason='Tekrar')
            minute = 16
            self.action(bantlama, 'bantlama', 'shift-end')
            self.assertEqual(supervisor.get(url).json()['date'], '2026-11-27')
            daily = board()
            taping = daily['bantlama']
            self.assertEqual((taping['total'], taping['quality']['rework'], taping['hourly'][0]), (1, 1, 1))
            self.assertEqual(taping['status'], 'stopped')
            self.assertEqual(taping['work'], {'activeMs': 480_000, 'stoppedMs': 120_000, 'maintenanceMs': 300_000,
                                            'idleMs': 60_000, 'stopCount': 2, 'reasons': ['Besleme bekliyor', 'Merdane kontrolü']})
            self.assertEqual((taping['workers'][0]['count'], taping['workers'][0]['activeMs']), (1, 480_000))
            self.assertIsNotNone(taping['workers'][0]['end'])
            self.assertEqual((daily['tekniker']['total'], daily['tekniker']['work']['activeMs']), (1, 300_000))
            task = daily['tekniker']['tasks'][0]
            self.assertEqual((task['id'], task['status'], task['activeMs']), (issue, 'resolved', 300_000))

    def test_manual_cut_replay_preserves_quantity_and_source_across_restart(self):
        self.action(self.admin, 'giyotin', 'shift-start', operator='Örnek Operatör')
        fields = dict(color='blue', count=2, lot='KESIM-TEST', length=100, result='good', shield=True,
                      orderId='WO-2026-0456', requestId='cut-request')
        self.action(self.admin, 'giyotin', 'cut', 409, **{**fields, 'orderId': 'WO-2026-0457'})
        first = self.action(self.admin, 'giyotin', 'cut', **fields)['board']
        self.assertEqual(first['cut']['blue'], 36)
        record = first['cutLog'][0]
        self.assertEqual((record['orderId'], record['source']), ('WO-2026-0456', 'manual'))
        self.assertTrue(record['recordedAt'].endswith('+00:00'))
        self.assertNotIn('recordedAt', first['cutLog'][-1])

        self.app = app_module.create_app()
        admin = self.actor('admin')
        replay = self.action(admin, 'giyotin', 'cut', **fields)['board']
        self.assertEqual(replay['cut'], first['cut'])
        self.assertEqual(replay['cutLog'], first['cutLog'])
        self.action(admin, 'giyotin', 'cut', 409, **{**fields, 'count': 3})
        scrap = self.action(admin, 'giyotin', 'cut', **{**fields, 'requestId': 'fire', 'result': 'scrap'})['board']
        self.assertEqual(scrap['cut'], first['cut'])
        self.assertEqual(scrap['cutLog'][0]['result'], 'scrap')

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

    def test_bantlama_stepper_is_a_fixed_card_with_no_custom_steps_required(self):
        card = {'kind': 'stepper', 'title': 'İş Adımları', 'size': 'full', 'source': 'fixed'}
        template = {'title': 'Bantlama', 'cards': [card]}
        draft = {'revision': 0, 'design': template}
        self.assertEqual(self.admin.put('/api/workspace/templates/kaplama', json=draft).status_code, 422)
        self.assertEqual(self.admin.put('/api/workspace/templates/bantlama', json=draft).status_code, 200)
        published = self.admin.post('/api/workspace/templates/bantlama/publish', json={'revision': 1})
        self.assertEqual(published.status_code, 200, published.text)
        self.assertEqual(published.json()['published']['design']['cards'][0]['kind'], 'stepper')

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

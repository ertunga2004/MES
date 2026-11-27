import os
from pathlib import Path
import secrets
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from mes_web import app as app_module
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

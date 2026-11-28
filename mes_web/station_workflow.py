"""Server-side station fixture used by paired tablets and staff observation."""

from contextlib import closing
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sqlite3
from threading import RLock
import time

from fastapi import HTTPException

from .station_access import STATIONS


COLORS = {'blue': 'Mavi', 'red': 'Kırmızı', 'yellow': 'Sarı'}
OUTCOMES = {'good', 'rework', 'scrap', 'allowed'}
TAPING_STEPS = ['Bant rengini doğrula', 'Kutu kodunu tara', 'Bant uzunluğunu ölç', 'Kalite kontrolünü tamamla']
STATION_DATA = {
    'bantlama': ('cut', 'used', 'activeBox', 'boxes', 'wip'),
    'giyotin': ('cut', 'used', 'cutLog'),
    'kaplama': ('coating',),
    'konveyor': ('boxes', 'conveyorCheck'),
    'paketleme': ('boxes', 'packed', 'carton'),
    'tekniker': ('faults',),
    'kalite': ('boxes', 'qualityLog'),
    'malzeme': ('materials', 'requests', 'dispatches'),
}


def initial_state():
    return {
        'revision': 0,
        'orders': [
            {'id': 'WO-2026-0456', 'customer': 'ABC Ltd.', 'status': 'active', 'qty': 50},
            {'id': 'WO-2026-0457', 'customer': 'XYZ A.Ş.', 'status': 'queued', 'qty': 30},
            {'id': 'WO-2026-0458', 'customer': 'DEF Tic.', 'status': 'queued', 'qty': 40},
        ],
        'goals': {'blue': 24, 'red': 16, 'yellow': 10},
        'cut': {'blue': 34, 'red': 19, 'yellow': 11},
        'used': {'blue': 26, 'red': 14, 'yellow': 6},
        'packed': {'blue': 10, 'red': 5, 'yellow': 3},
        'boxes': [
            {'id': 'KUTU-784', 'color': 'yellow', 'stage': 'packed', 'measurement': 'OLC-084', 'outcome': 'good'},
            {'id': 'KUTU-785', 'color': 'blue', 'stage': 'exited', 'measurement': 'OLC-085', 'outcome': 'good'},
            {'id': 'KUTU-786', 'color': 'red', 'stage': 'exited', 'measurement': 'OLC-086', 'outcome': 'good'},
            {'id': 'KUTU-787', 'color': 'yellow', 'stage': 'transit', 'measurement': 'OLC-087', 'outcome': 'good'},
            {'id': 'KUTU-788', 'color': 'blue', 'stage': 'handoff', 'outcome': 'good'},
            {'id': 'KUTU-783', 'color': 'red', 'stage': 'rejected', 'outcome': 'rework'},
            {'id': 'KUTU-782', 'color': 'blue', 'stage': 'rejected', 'outcome': 'scrap'},
        ],
        'activeBox': None, 'shifts': {}, 'templates': {}, 'templateRecords': {},
        'carton': {'stage': 'open', 'reason': ''},
        'cutLog': [{'color': 'blue', 'count': 12, 'lot': 'BNT-M-026', 'result': 'good'}],
        'coating': {'total': 12, 'target': 50, 'records': []},
        'conveyorCheck': None,
        'wip': [{'name': 'Giriş bekleme alanı', 'occupied': 1, 'capacity': 5}, {'name': 'Çıkış bekleme alanı', 'occupied': 0, 'capacity': 3}],
        'qualityLog': [],
        'faults': [
            {'id': 'ARZ-014', 'station': 'Bantlama', 'text': 'Bant besleme merdanesi kontrol bekliyor.', 'status': 'open', 'reply': '', 'kind': 'fault'},
            {'id': 'ARZ-013', 'station': 'Konveyör', 'text': 'Çıkış sensörü kontrol edilmeli.', 'status': 'accepted', 'reply': '', 'kind': 'fault'},
        ],
        'materials': {'blue': 12, 'red': 8, 'yellow': 3}, 'requests': [], 'dispatches': [],
    }


def require(condition, message, status=409):
    if not condition:
        raise HTTPException(status, message)


def text(fields, key, label, limit=240):
    value = fields.get(key)
    require(isinstance(value, str) and 0 < len(value.strip()) <= limit, f'{label} girin.', 422)
    return value.strip()


def number(fields, key, label, *, integer=False, zero=False):
    try:
        value = float(fields.get(key))
    except (ValueError, TypeError, OverflowError):
        value = math.nan
    require(math.isfinite(value) and (value >= 0 if zero else value > 0) and value <= 10000 and
            (not integer or value.is_integer()), f'Geçerli {label} girin.', 422)
    return int(value) if integer else value


def choice(fields, key, options, label):
    value = fields.get(key)
    require(isinstance(value, str) and value in options, f'{label} seçin.', 422)
    return value


def confirmed(fields, key, label):
    require(fields.get(key) is True or fields.get(key) == 'on', f'{label} onaylanmalı.', 422)


def box_at(state, fields, stage):
    box = next((row for row in state['boxes'] if row['id'] == fields.get('box') and row['stage'] == stage), None)
    require(box is not None, 'Kutu seçili işlem için hazır değil.')
    return box


def shift(state, station, action, fields):
    if action == 'shift-start':
        require(station not in state['shifts'], 'Bu istasyonun vardiyası zaten açık.')
        state['shifts'][station] = {'operator': text(fields, 'operator', 'Operatör adını', 80), 'startedAt': int(time.time() * 1000)}
        return 'Vardiya başlatıldı.'
    require(station in state['shifts'], 'Açık vardiya bulunamadı.')
    require(station != 'bantlama' or state['activeBox'] is None, 'Vardiya kapanmadan önce açık kutuyu tamamlayın.')
    del state['shifts'][station]
    return 'Vardiya bitirildi.'


def alert(state, station, action, fields):
    description = text(fields, 'description', 'Açıklama')
    identifier = f'ARZ-{15 + len(state["faults"]) - 2:03d}'
    state['faults'].insert(0, {'id': identifier, 'station': STATIONS[station], 'kind': action,
                               'text': description, 'status': 'open', 'reply': ''})
    return f'{identifier} Tekniker ekranına iletildi.'


def cutting(state, action, fields):
    color = choice(fields, 'color', COLORS, 'Renk')
    count = number(fields, 'count', 'kesim adedi', integer=True)
    lot = text(fields, 'lot', 'Kesim partisini', 60)
    length = number(fields, 'length', 'uzunluk ölçümü')
    result = choice(fields, 'result', {'good', 'scrap'}, 'Ölçüm sonucunu')
    confirmed(fields, 'shield', 'Koruyucu kalkan kontrolü')
    record = dict(color=color, count=count, lot=lot, length=length, result=result)
    if state.get('erpOrder'):
        order_id = text(fields, 'orderId', 'İş emrini', 60)
        request_id = text(fields, 'requestId', 'Kesim kayıt kimliğini', 64)
        record.update(orderId=order_id, requestId=request_id, source='manual')
        previous = next((row for row in state['cutLog'] if row.get('requestId') == request_id), None)
        if previous is not None:
            require(all(previous.get(key) == value for key, value in record.items()),
                    'Bu kayıt kimliği farklı bir kesim için kullanılmış.')
            return 'Kesim kaydı daha önce alındı.'
        require(state['orders'][0]['id'] == order_id, 'Aktif örnek iş emri değişti. Ekranı yenileyin.')
    if result == 'good':
        remaining = state['goals'][color] * 2 - state['cut'][color]
        require(count <= remaining, f'Bu renkte kesim hedefinden {remaining} bant kaldı.')
        state['cut'][color] += count
    if state.get('erpOrder'):
        record['recordedAt'] = datetime.now(timezone.utc).isoformat()
    state['cutLog'].insert(0, record)
    return 'Kesim kontrolü kaydedildi.'


def coating(state, action, fields):
    batch = text(fields, 'batch', 'Kaplama partisini', 60)
    tank = text(fields, 'tank', 'Tank kodunu', 60)
    chemical = text(fields, 'chemical', 'Kimyasal lotunu', 60)
    concentration = number(fields, 'concentration', 'konsantrasyon ölçümü', zero=True)
    thickness = number(fields, 'thickness', 'kalınlık ölçümü', zero=True)
    drying = number(fields, 'drying', 'kurutma süresi', zero=True)
    quantity = number(fields, 'quantity', 'parça adedi', integer=True)
    outcome = choice(fields, 'outcome', {'good', 'scrap'}, 'Görsel kontrol sonucunu')
    summary = state['coating']
    require(not any(row['batch'] == batch for row in summary['records']), 'Bu kaplama partisi kaydedilmiş.')
    if outcome == 'good':
        require(summary['total'] + quantity <= summary['target'], 'Kaplama hedefi aşılıyor.')
        summary['total'] += quantity
    summary['records'].insert(0, dict(batch=batch, chemical=chemical, tank=tank, concentration=concentration,
                                      thickness=thickness, drying=drying, quantity=quantity, outcome=outcome))
    return 'Kaplama kontrolü kaydedildi.'


def taping(state, action, fields):
    box = state['activeBox']
    now = int(time.time() * 1000)
    if action == 'start':
        color = choice(fields, 'color', COLORS, 'Bant rengini')
        identifier = text(fields, 'box', 'Kutu kodunu', 60)
        require(not box and not any(row['id'] == identifier for row in state['boxes']), 'Açık veya yinelenen kutu kaydı var.')
        require(state['cut'][color] - state['used'][color] >= 2, 'Bu renk için iki kesilmiş bant gerekiyor.')
        state['used'][color] += 2
        state['activeBox'] = {'id': identifier, 'color': color, 'steps': [False] * len(TAPING_STEPS), 'activeMs': 0,
                              'since': now, 'paused': False, 'pauseReason': ''}
        return f'{identifier} için bantlama başladı.'
    require(box is not None and box['id'] == fields.get('activeBoxId'), 'Açık kutu değişti. Ekranı yenileyin.')
    if action == 'resume':
        require(box['paused'], 'Duraklatılmış kutu yok.')
        box.update(paused=False, since=now, pauseReason='')
        return 'Bantlama devam ediyor.'
    require(not box['paused'], 'Önce bantlamaya devam edin.')
    if action == 'pause':
        reason = text(fields, 'reason', 'Duraklatma nedenini')
        box.update(activeMs=box['activeMs'] + max(0, now - box['since']), paused=True, pauseReason=reason)
        return 'Bantlama duraklatıldı.'
    if action == 'step':
        index = fields.get('index')
        value = fields.get('checked')
        require(type(index) is int and 0 <= index < len(TAPING_STEPS) and type(value) is bool, 'Adım geçersiz.', 422)
        box['steps'][index] = value
        return 'Kontrol adımı güncellendi.'
    outcome = choice(fields, 'outcome', {'good', 'rework', 'scrap'}, 'Kontrol sonucunu')
    if outcome == 'good':
        require(all(box['steps']), 'Sağlam teslim için tüm adımları tamamlayın.')
        length = number(fields, 'length', 'bant uzunluğu')
        reason = ''
    else:
        length = None
        reason = text(fields, 'reason', 'Kalite gerekçesini')
    state['boxes'].append(dict(id=box['id'], color=box['color'], stage='handoff' if outcome == 'good' else 'rejected',
                               outcome=outcome, length=length, reason=reason, completedAt=now if outcome != 'good' else None,
                               taping={'at': now}))
    state['activeBox'] = None
    return f'{box["id"]} bantlama sonucu kaydedildi.'


def conveyor(state, action, fields):
    if action == 'check':
        speed = number(fields, 'speed', 'gözlenen hız', zero=True)
        confirmed(fields, 'sensor', 'Sensör kontrolü')
        confirmed(fields, 'stop', 'Acil durdurma kontrolü')
        state['conveyorCheck'] = {'speed': speed, 'sensor': True, 'stop': True}
        return 'Konveyör kontrolü kaydedildi.'
    if action == 'match':
        box = box_at(state, fields, 'handoff')
        measurement = text(fields, 'measurement', 'Hat ölçüm kodunu', 60)
        require(not any(row.get('measurement') == measurement for row in state['boxes']), 'Bu ölçüm başka kutuyla eşleşmiş.')
        box.update(stage='transit', measurement=measurement)
        return f'{box["id"]} hat ölçümüyle eşleştirildi.'
    box = box_at(state, fields, 'transit')
    box.update(stage='exited', completedAt=int(time.time() * 1000))
    return f'{box["id"]} çıkışı doğrulandı.'


def packing(state, action, fields):
    carton = state['carton']
    if action == 'resume':
        require(carton['stage'] == 'parked', 'Ayrılmış koli yok.')
        carton.update(stage='open', reason='')
        return 'Paketlemeye devam ediliyor.'
    require(carton['stage'] == 'open', 'Önce koliyi açın.')
    complete = state['goals'] == state['packed']
    if action == 'seal':
        require(complete, 'Koliyi kapatmak için tüm renk hedeflerini tamamlayın.')
        carton['stage'] = 'sealed'
        return 'Koli kapatıldı.'
    if action == 'park':
        require(not complete, 'Yalnız eksik koli ayrılabilir.')
        carton.update(stage='parked', reason=text(fields, 'reason', 'Eksik koli nedenini'))
        return 'Eksik koli ayrıldı.'
    box = box_at(state, fields, 'exited')
    color = box['color']
    require(box['outcome'] == 'good' and state['packed'][color] < state['goals'][color], 'Kutu sağlam ve renk hedefi açık olmalı.')
    size = text(fields, 'size', 'Kutu boyutunu', 60)
    label = text(fields, 'label', 'Etiket kodunu', 60)
    weight = number(fields, 'weight', 'ağırlık')
    require(number(fields, 'count', 'kutu sayısı', integer=True) == 1, 'Her kayıtta tek kutu eklenir.', 422)
    confirmed(fields, 'protected', 'Kutu koruması')
    state['packed'][color] += 1
    box.update(stage='packed', packing=dict(size=size, label=label, weight=weight))
    return f'{box["id"]} koliye eklendi.'


def technician(state, action, fields):
    fault = next((row for row in state['faults'] if row['id'] == fields.get('fault')), None)
    require(fault is not None, 'Bildirim bulunamadı.', 404)
    if action == 'accept':
        require(fault['status'] == 'open', 'Yalnız açık bildirim kabul edilebilir.')
        fault['status'] = 'accepted'
        return 'Bildirim kabul edildi.'
    require(fault['status'] == 'accepted', 'Önce bildirimi kabul edin.')
    if action == 'reply':
        fault['reply'] = text(fields, 'reply', 'Teknik yanıtı')
        return 'Teknik yanıt kaydedildi.'
    category = text(fields, 'category', 'Arıza türünü', 60)
    parts = text(fields, 'parts', 'Yedek parça durumunu', 60)
    intervention = text(fields, 'intervention', 'Müdahaleyi')
    downtime = number(fields, 'downtime', 'duruş süresi', integer=True, zero=True)
    outcome = choice(fields, 'outcome', {'repaired', 'waiting'}, 'Müdahale sonucunu')
    if outcome == 'repaired':
        confirmed(fields, 'tested', 'Test sonucu')
        fault['status'] = 'resolved'
    fault['result'] = dict(category=category, parts=parts, intervention=intervention, downtime=downtime, outcome=outcome)
    return 'Müdahale sonucu kaydedildi.'


def quality(state, action, fields):
    box = box_at(state, fields, 'exited')
    outcome = choice(fields, 'outcome', OUTCOMES, 'Kalite kararını')
    instrument = text(fields, 'instrument', 'Ölçüm aletini', 60)
    measured = number(fields, 'measured', 'ölçüm', zero=True)
    tolerance = text(fields, 'tolerance', 'Tolerans bilgisini', 60)
    visual = choice(fields, 'visual', {'good', 'scrap'}, 'Görsel kontrol sonucunu')
    reason = text(fields, 'reason', 'Karar gerekçesini')
    require(outcome != 'good' or visual == 'good', 'Görsel kontrol red iken uygun kararı verilemez.', 422)
    state['qualityLog'].insert(0, dict(box=box['id'], previous=box['outcome'], outcome=outcome, reason=reason,
                                       instrument=instrument, measured=measured, tolerance=tolerance, visual=visual))
    box['outcome'] = outcome
    return 'Kalite kararı kaydedildi.'


def materials(state, action, fields):
    color = choice(fields, 'color', COLORS, 'Bant rengini')
    quantity = number(fields, 'quantity', 'malzeme adedi', integer=True)
    if action == 'request':
        reason = text(fields, 'reason', 'Talep nedenini')
        identifier = f'MLZ-{len(state["requests"]) + 1:03d}'
        state['requests'].insert(0, dict(id=identifier, color=color, quantity=quantity, reason=reason, received=False))
        return 'Malzeme talebi kaydedildi.'
    barcode = text(fields, 'barcode', 'Barkodu', 60)
    location = text(fields, 'location', 'Lokasyonu', 80)
    confirmed(fields, 'condition', 'Malzemenin sevke uygunluğu')
    require(quantity <= state['materials'][color], 'Stok sevk miktarını karşılamıyor.')
    state['materials'][color] -= quantity
    state['dispatches'].insert(0, dict(barcode=barcode, location=location, color=color, quantity=quantity))
    return 'Malzeme sevki kaydedildi.'


ACTIONS = {
    'giyotin': (cutting, {'cut'}), 'kaplama': (coating, {'coat'}),
    'bantlama': (taping, {'start', 'step', 'pause', 'resume', 'finish'}),
    'konveyor': (conveyor, {'check', 'match', 'exit'}), 'paketleme': (packing, {'pack', 'park', 'resume', 'seal'}),
    'tekniker': (technician, {'accept', 'reply', 'resolve'}), 'kalite': (quality, {'classify'}),
    'malzeme': (materials, {'request', 'dispatch'}),
}


def template_record(state, station, fields):
    template = state['templates'].get(station, {}).get('published')
    require(template and str(template['version']) == fields.get('version'), 'Yayın değişti. Ekranı yenileyin.')
    values = []
    for index, step in enumerate(template['design']['steps']):
        key = f'step-{index}'
        value = fields.get(key)
        if step['kind'] == 'check':
            if step['required']:
                confirmed(fields, key, step['label'])
            value = value == 'on'
        elif value or step['required']:
            if step['kind'] == 'choice':
                value = choice(fields, key, step['options'], step['label'])
            elif step['kind'] == 'number':
                value = number(fields, key, step['label'], zero=True)
            else:
                value = text(fields, key, step['label'])
        values.append(value)
    options = template['design']['result_options']
    result = choice(fields, 'result', options, 'Şablon sonucunu') if options else ''
    state['templateRecords'][station] = {'version': template['version'], 'values': values, 'result': result}
    return 'Yayınlanan kontrol listesi kaydedildi.'


class StationWorkflow:
    def __init__(self):
        self.lock = RLock()
        self.state = initial_state()
        raw_path = os.environ.get('MES_WEB_WORKSPACE_STATE_PATH')
        self.path = Path(raw_path) if raw_path else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(self.path)) as conn, conn:
                conn.execute('CREATE TABLE IF NOT EXISTS station_state (id INTEGER PRIMARY KEY, data TEXT NOT NULL)')
                conn.execute('INSERT OR IGNORE INTO station_state VALUES (1, ?)', (json.dumps(self.state),))

    def read(self):
        with self.lock:
            if not self.path:
                return deepcopy(self.state)
            with closing(sqlite3.connect(self.path)) as conn:
                return json.loads(conn.execute('SELECT data FROM station_state WHERE id=1').fetchone()[0])

    def edit(self, update):
        with self.lock:
            if not self.path:
                state = deepcopy(self.state)
                result = update(state)
                state['revision'] += 1
                self.state = state
                return result, state
            with closing(sqlite3.connect(self.path)) as conn, conn:
                conn.execute('BEGIN IMMEDIATE')
                state = json.loads(conn.execute('SELECT data FROM station_state WHERE id=1').fetchone()[0])
                result = update(state)
                state['revision'] += 1
                conn.execute('UPDATE station_state SET data=? WHERE id=1', (json.dumps(state),))
                return result, state

    def action(self, station, action, fields):
        def update(state):
            if action in {'shift-start', 'shift-end'}:
                return shift(state, station, action, fields)
            require(station in state['shifts'], 'Bu işleme başlamadan önce vardiyayı açın.')
            if action in {'fault', 'help'}:
                return alert(state, station, action, fields)
            if action == 'template-record':
                return template_record(state, station, fields)
            handler, allowed = ACTIONS[station]
            require(action in allowed, 'Bu işlem seçili istasyona ait değil.', 403)
            return handler(state, action, fields)

        return self.edit(update)

    @staticmethod
    def station_board(state, station):
        keys = ('revision', 'goals', *STATION_DATA[station])
        view = {key: state[key] for key in keys}
        view['orders'] = state['orders'][:1]
        view['shift'] = state['shifts'].get(station)
        view['template'] = state['templates'].get(station, {}).get('published')
        view['templateRecord'] = state['templateRecords'].get(station)
        return view

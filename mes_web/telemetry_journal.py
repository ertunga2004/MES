"""Persistent history for the observations and connection events received by MES."""

import csv
import hashlib
import io
import json
import math
import sqlite3
from contextlib import closing, contextmanager
from datetime import date, datetime, time, timedelta, timezone
from threading import Lock

from .parsers import parse_vision_event


LOCAL_TIME = timezone(timedelta(hours=3))
READ_EVENTS = {'line_crossed', 'read_success', 'read_failed', 'read_error', 'decode_failed'}
FAILURES = {'read_failed', 'read_error', 'decode_failed', 'failed', 'failure', 'error', 'no_read'}
KNOWN_COLORS = {'red', 'yellow', 'blue', 'green', 'orange', 'purple', 'white', 'black'}
FILTERS = {'product': 'product_code', 'code': 'code', 'order': 'order_id', 'q': 'search_text'}
CSV_FIELDS = ('id', 'day', 'clock', 'camera', 'item_id', 'code', 'product_code', 'description', 'order_id', 'result', 'quality', 'duration_ms', 'error')
CSV_HEADER = ('Kayıt no', 'Tarih', 'Saat', 'Kamera', 'Ürün ID', 'Barkod / QR', 'Ürün kodu', 'Tespit', 'İş emri', 'Sonuç', 'Kalite', 'Okuma (ms)', 'Hata')


def local_stamp(value):
    try:
        stamp = datetime.fromisoformat(value)
        return stamp.astimezone(LOCAL_TIME) if stamp.tzinfo else None
    except (TypeError, ValueError):
        return None


def text(value):
    return str(value).strip() if isinstance(value, (str, int, float)) and not isinstance(value, bool) else ''


def camera_record(wire, enriched, received_at, device_hint=''):
    parsed = parse_vision_event(wire)
    if not parsed or parsed['event_type'] not in READ_EVENTS:
        return None
    raw = parsed['raw']
    resolved = parse_vision_event(enriched) or parsed
    extra = resolved['raw']
    kind = parsed['event_type']
    camera = text(raw.get('camera_id') or raw.get('device_name'))
    source_id = text(raw.get('event_id'))
    identity = [camera, source_id] if source_id else [camera, kind, parsed['track_id'], parsed['vision_observed_at'], raw.get('frame_index')]
    if not source_id and not (parsed['vision_observed_at'] and (parsed['track_id'] or raw.get('frame_index') is not None)):
        identity.append(raw)
    record_id = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()
    clock = local_stamp(parsed['vision_observed_at']) or local_stamp(received_at)
    if clock is None:
        return None
    error = text(raw.get('error') or raw.get('error_message'))
    code = text(raw.get('barcode') or raw.get('qr_code'))
    product = text(raw.get('product_code'))
    observed = raw.get('success')
    result = text(raw.get('result')).lower()
    if kind in FAILURES or result in FAILURES or observed is False:
        outcome = 'failed'
    elif observed is True or kind == 'read_success' or result in {'success', 'ok'} or code:
        outcome = 'success'
    elif parsed['color'] in KNOWN_COLORS and resolved['confidence_tier'] != 'low' and result not in {'uncertain', 'unverified'}:
        outcome = 'success'
    else:
        outcome = 'uncertain'
    raw_duration = raw.get('read_duration_ms')
    duration = raw_duration if type(raw_duration) in (int, float) and 0 <= raw_duration < math.inf else None
    matched = resolved['correlation_status'] == 'matched'
    return {'id': record_id, 'at': clock.isoformat(timespec='milliseconds'), 'day': clock.date().isoformat(),
            'clock': clock.time().isoformat(timespec='seconds'), 'camera': camera or device_hint,
            'item_id': parsed['item_id'] or (resolved['item_id'] if matched else '') or '',
            'measure_id': parsed['measure_id'] or (resolved['measure_id'] if matched else '') or '', 'code': code,
            'product_code': product, 'description': text(raw.get('label') or raw.get('color_name')),
            'order_id': text(raw.get('work_order_id') or (extra.get('work_order_id') if matched else '')),
            'quality': text(raw.get('quality_result') or (extra.get('quality_result') if matched else '')),
            'duration_ms': duration, 'error': error, 'result': outcome, 'event': kind,
            'correlation': resolved['correlation_status'], 'track_id': parsed['track_id'],
            'image_url': None, 'raw': wire if isinstance(wire, str) else json.dumps(raw, ensure_ascii=False)}


def filter_query(params):
    clauses, values = [], []
    for key, column, comparison, convert in (
        ('date_from', 'day', '>=', date.fromisoformat), ('date_to', 'day', '<=', date.fromisoformat),
        ('time_from', 'clock', '>=', time.fromisoformat), ('time_to', 'clock', '<=', time.fromisoformat),
    ):
        value = params.get(key)
        if value:
            parsed = convert(value)
            if isinstance(parsed, time) and parsed.tzinfo is not None:
                raise ValueError('Saat aralığı yerel saat olmalı.')
            boundary = parsed.isoformat()
            if isinstance(parsed, time) and len(value) == 5 and comparison == '<=':
                boundary = parsed.replace(second=59).isoformat()
            clauses.append(f'{column} {comparison} ?')
            values.append(boundary)
    for key, column in FILTERS.items():
        if value := params.get(key, '').strip():
            clauses.append(f'instr({column}, ?) > 0')
            values.append(value.casefold())
    if result := params.get('result'):
        if result not in {'success', 'failed', 'uncertain'}:
            raise ValueError('Geçersiz okuma sonucu.')
        clauses.append('result = ?')
        values.append(result)
    return (' WHERE ' + ' AND '.join(clauses) if clauses else ''), values


class TelemetryJournal:
    def __init__(self, path):
        self.path = path
        self._ready = False
        self._lock = Lock()

    @contextmanager
    def connection(self):
        if not self._ready:
            with self._lock:
                if not self._ready:
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    with closing(sqlite3.connect(self.path)) as conn, conn:
                        conn.execute('PRAGMA journal_mode=WAL').fetchone()
                        conn.executescript('''
                            CREATE TABLE IF NOT EXISTS camera_records (
                                id TEXT PRIMARY KEY, at TEXT NOT NULL, day TEXT NOT NULL, clock TEXT NOT NULL,
                                result TEXT NOT NULL, product_code TEXT NOT NULL, code TEXT NOT NULL,
                                order_id TEXT NOT NULL, search_text TEXT NOT NULL, data TEXT NOT NULL
                            );
                            CREATE INDEX IF NOT EXISTS camera_time ON camera_records(at DESC, id DESC);
                            CREATE INDEX IF NOT EXISTS camera_day ON camera_records(day, result);
                            CREATE INDEX IF NOT EXISTS camera_link ON camera_records(
                                json_extract(data, '$.item_id'), json_extract(data, '$.measure_id'), at
                            );
                            CREATE TABLE IF NOT EXISTS system_events (
                                id INTEGER PRIMARY KEY, at TEXT NOT NULL, device TEXT NOT NULL,
                                kind TEXT NOT NULL, message TEXT NOT NULL, level TEXT NOT NULL, code TEXT NOT NULL
                            );
                        ''')
                    self._ready = True
        with closing(sqlite3.connect(self.path, check_same_thread=False)) as conn, conn:
            conn.row_factory = sqlite3.Row
            yield conn

    def save_camera(self, row):
        fields = [row[key] for key in ('id', 'at', 'day', 'clock', 'result')]
        fields.extend(row[key].casefold() for key in ('product_code', 'code', 'order_id'))
        fields.append(' '.join(text(row.get(key)) for key in (*CSV_FIELDS, 'track_id', 'correlation')).casefold())
        fields.append(json.dumps(row, ensure_ascii=False))
        with self.connection() as conn:
            return bool(conn.execute('INSERT OR IGNORE INTO camera_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', fields).rowcount)

    def link_camera(self, item_id, measure_id, order_id, quality, started_at, completed_at):
        start, end = local_stamp(started_at), local_stamp(completed_at)
        if not item_id or not measure_id or not start or not end:
            return
        with self.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            rows = conn.execute('''SELECT id, data FROM camera_records WHERE at BETWEEN ? AND ?
                AND json_extract(data, '$.item_id') = ? AND json_extract(data, '$.measure_id') = ?
                AND json_extract(data, '$.correlation') = 'matched' ''',
                (start.isoformat(timespec='milliseconds'), end.isoformat(timespec='milliseconds'), item_id, measure_id)).fetchall()
            for existing in rows:
                row = json.loads(existing['data'])
                row.update(order_id=order_id or row['order_id'], quality=quality or row['quality'])
                search = ' '.join(text(row.get(key)) for key in (*CSV_FIELDS, 'track_id', 'correlation')).casefold()
                conn.execute('UPDATE camera_records SET order_id=?, search_text=?, data=? WHERE id=?',
                             (row['order_id'].casefold(), search, json.dumps(row, ensure_ascii=False), row['id']))

    def camera_page(self, params, *, page, limit, today):
        where, values = filter_query(params)
        with self.connection() as conn:
            conn.execute('BEGIN')
            count = conn.execute(f'SELECT count(*) FROM camera_records{where}', values).fetchone()[0]
            page = min(page, max(1, (count + limit - 1) // limit))
            rows = conn.execute(f'SELECT data FROM camera_records{where} ORDER BY at DESC, id DESC LIMIT ? OFFSET ?',
                                (*values, limit, (page - 1) * limit)).fetchall()
            totals = {row['result']: row['count'] for row in conn.execute(
                'SELECT result, count(*) AS count FROM camera_records WHERE day = ? GROUP BY result', (today,))}
            last_at = conn.execute('SELECT at FROM camera_records ORDER BY at DESC LIMIT 1').fetchone()
        items = [json.loads(row['data']) for row in rows]
        for item in items:
            item.pop('raw')
        return {'items': items, 'count': count, 'page': page, 'limit': limit, 'today': totals,
                'last_at': last_at[0] if last_at else None}

    def camera_detail(self, record_id):
        with self.connection() as conn:
            row = conn.execute('SELECT data FROM camera_records WHERE id = ?', (record_id,)).fetchone()
        return json.loads(row['data']) if row else None

    def camera_csv(self, filters):
        where, values = filters

        def csv_cell(value):
            string = '' if value is None else str(value)
            return "'" + string if string.lstrip().startswith(('=', '+', '-', '@')) else string

        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')
        writer.writerow(CSV_HEADER)
        yield '\ufeff' + output.getvalue()
        with self.connection() as conn:
            for entry in conn.execute(f'SELECT data FROM camera_records{where} ORDER BY at DESC, id DESC', values):
                row = json.loads(entry['data'])
                output.seek(0)
                output.truncate(0)
                writer.writerow([csv_cell(row.get(key)) for key in CSV_FIELDS])
                yield output.getvalue()

    def system_event(self, at, device, kind, message, level='info', code=''):
        with self.connection() as conn:
            conn.execute('INSERT INTO system_events (at, device, kind, message, level, code) VALUES (?, ?, ?, ?, ?, ?)',
                         (at, device, kind, message, level, code))

    def system_events(self):
        with self.connection() as conn:
            return [dict(row) for row in conn.execute('SELECT * FROM system_events ORDER BY id DESC LIMIT 80')]

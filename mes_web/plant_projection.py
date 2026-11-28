"""Read models for the conveyor control center and equipment status."""

from datetime import datetime, timedelta
from statistics import median

from .telemetry_journal import LOCAL_TIME, local_stamp


def fresh(stamp, now, seconds):
    parsed = local_stamp(stamp)
    return bool(parsed and timedelta(0) <= now - parsed <= timedelta(seconds=seconds))


def elapsed_ms(start, end):
    left, right = local_stamp(start), local_stamp(end)
    return round((right - left).total_seconds() * 1000) if left and right and right > left else None


def runtime_projection(state, current):
    items = state.get('itemsById') or {}
    completed = sorted((row for row in items.values() if row.get('completed_at')), key=lambda row: row['completed_at'], reverse=True)
    today = current.astimezone(LOCAL_TIME).date()
    daily = [row for row in completed if (stamp := local_stamp(row['completed_at'])) and stamp.date() == today]
    cycle_rows = [(row['completed_at'], elapsed_ms(row.get('picked_at'), row['completed_at'])) for row in completed[:10]]
    cycles = [duration for stamp, duration in cycle_rows if duration and fresh(stamp, current, 600)]
    queued = [items[key] for key in state.get('queueOrder', []) if key in items and not items[key].get('completed_at')]
    order_id = (state.get('workOrders') or {}).get('activeOrderId')
    order_times = [row['completed_at'] for row in completed if order_id and row.get('work_order_id') == order_id][:8]
    intervals = [elapsed_ms(earlier, later) for later, earlier in zip(order_times, order_times[1:])]
    intervals = [duration for duration in intervals if duration and duration <= 600_000]
    fault = state.get('activeFault') or {}
    maintenance = state.get('maintenance') or {}
    sessions = [maintenance.get('openingSession') or {}, maintenance.get('closingSession') or {}]
    active_maintenance = next((row for row in sessions if row.get('status') == 'active'), None)
    return {
        'local_day': today.isoformat(), 'daily_completed': len(daily),
        'measured_today': sum(bool((stamp := local_stamp(row.get('measured_at'))) and stamp.date() == today) for row in items.values()),
        'queue_item': queued[0].get('item_id') if queued else None,
        'robot_item': next((row.get('item_id') for row in queued if row.get('picked_at')), None),
        'last_completed': daily[0].get('item_id') if daily else None,
        'last_cycle_ms': cycles[0] if cycles else None, 'cycle_median_ms': round(median(cycles)) if len(cycles) >= 3 else None,
        'rate_ms': round(median(intervals)) if len(intervals) >= 3 and fresh(order_times[0], current, 600) else None,
        'rate_order_id': order_id, 'cycle_at': cycle_rows[0][0] if cycle_rows else None,
        'fault_code': fault.get('reasonCode'), 'fault_id': fault.get('faultId'),
        'maintenance': active_maintenance,
        'devices': [{'name': row.get('deviceName') or key, 'id': key, 'at': row.get('lastSeenAt'), 'station': row.get('boundStationId')}
                    for key, row in (state.get('deviceRegistry') or {}).items()],
    }


def equipment(snapshot, now, timeout):
    connection = snapshot['connection']
    timestamps = snapshot['timestamps']
    system = snapshot['system_status']
    hardware = snapshot['hardware_status']
    vision = snapshot['vision_ingest']
    runtime = snapshot['plant']
    b = connection['bridge']
    hb = connection['mega_heartbeat']
    status_at = timestamps['last_status_at']
    line_live = fresh(status_at, now, timeout)
    camera_at = timestamps['last_vision_ingest_at']
    camera_health = vision['runtime'].get('health_state')
    if camera_health in (None, '', 'offline'):
        camera_health = vision['status'].get('state')
    camera_tone = ('idle' if not vision['enabled'] or not camera_at else 'error' if not fresh(camera_at, now, timeout) or camera_health in {'offline', 'error'}
                   else 'warn' if camera_health == 'degraded' else 'ok')
    fault = snapshot['oee']['fault']

    def link(state, at):
        return 'Bağlı' if state == 'online' else 'Bağlantı kesik' if at else None

    def row(name, tone, at=None, connected=None, status=None, detail=None, code=None):
        return {'name': name, 'tone': tone, 'at': at, 'connection': connected, 'status': status, 'detail': detail, 'code': code}

    def machine(name, status, *, detail=None, code=None, maintenance=False):
        alarm = (line_live and status in {'fault', 'error', 'alarm'}) or bool(detail and name == 'Konveyör')
        tone = 'error' if alarm else 'maintenance' if maintenance else 'error' if status_at and not line_live else 'idle'
        if not alarm and not maintenance and line_live:
            tone = 'ok' if status not in {None, '', 'idle', 'off', 'stopped', 'stop', 'disabled', 'unknown'} or bool(detail) else 'idle'
        return row(name, tone, status_at, 'Mega üzerinden' if line_live else 'Telemetri eski' if status_at else None,
                   status if line_live else None, detail, code)

    drops = (b['drop_uart'] or 0) + (b['drop_pub'] or 0)
    return [
        row('Arduino Mega', 'ok' if hb['state'] == 'online' else 'error' if hb['last_seen_at'] else 'idle',
            hb['last_seen_at'], link(hb['state'], hb['last_seen_at']), system['system_state'] if line_live else None),
        row('ESP32 köprüsü', 'idle' if not b['last_seen_at'] else 'error' if b['state'] == 'offline' else 'warn' if b['state'] == 'degraded' or drops else 'ok',
            b['last_seen_at'], 'Kısıtlı' if b['state'] == 'degraded' else link(b['state'], b['last_seen_at']), b['state'] if b['last_seen_at'] else None,
            f"UART kaybı {b['drop_uart']} · MQTT kaybı {b['drop_pub']}" if drops else None),
        machine('Konveyör', system['conveyor_state'], detail=fault['reason'] if fault['active'] else None,
                code=runtime.get('fault_code'), maintenance=bool(runtime.get('maintenance'))),
        machine('Robot kol', system['robot_state']),
        machine('Renk sensörü', system['last_color'] if timestamps['last_log_at'] else None),
        machine('Limit anahtarları 22 / 23', None, detail=' / '.join('Basılı' if hardware[key] else 'Açık' for key in ('limit_22_pressed', 'limit_23_pressed')) if line_live and hardware['limit_22_pressed'] is not None and hardware['limit_23_pressed'] is not None else None),
        row('Raspberry / Kamera', camera_tone, camera_at, 'Telemetri alınıyor' if camera_tone in {'ok', 'warn'} else 'Telemetri kesik' if camera_tone == 'error' else None,
            camera_health if camera_tone in {'ok', 'warn'} else 'Devre dışı' if not vision['enabled'] else None),
        row('Giyotin', 'idle', status='Cihaz telemetrisi yok'),
        *[row(device['name'], 'idle', device['at'], status=device['station'] or 'Kayıtlı tablet') for device in runtime.get('devices', [])],
        *([] if runtime.get('devices') else [row('Operatör tabletleri', 'idle', status='Cihaz telemetrisi yok')]),
    ]

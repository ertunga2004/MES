"""Daily, read-only projections of timestamped station workspace records."""

from datetime import datetime, timedelta, timezone
from time import time

from .station_access import STATIONS


MONITORED_STATIONS = ('bantlama', 'paketleme', 'tekniker', 'giyotin')
# The workshop uses Türkiye's current year-round UTC+3 for production days.
WORKSHOP_TIME = timezone(timedelta(hours=3))


def local_time(stamp):
    return datetime.fromtimestamp(stamp / 1000, WORKSHOP_TIME)


def union_ms(intervals):
    total = 0
    end = 0
    for start, stop in sorted(intervals):
        if stop > max(start, end):
            total += stop - max(start, end)
            end = stop
    return total


def clip(intervals, start, end):
    return [(max(left, start), min(right, end)) for left, right in intervals if left < end and right > start]


def production_records(state, station):
    if station == 'giyotin':
        return [dict(at=int(datetime.fromisoformat(row['recordedAt']).timestamp() * 1000), count=row['count'],
                     outcome=row['result'], shiftStartedAt=row.get('shiftStartedAt'))
                for row in state['cutLog'] if row.get('recordedAt')]
    if station == 'tekniker':
        return [dict(row['intervention']['completion'], count=1) for row in state['faults']
                if row.get('intervention', {}).get('completion')]
    if station == 'paketleme':
        return [dict(at=row['packing']['recordedAt'], count=1, shiftStartedAt=row['packing'].get('shiftStartedAt'))
                for row in state['boxes'] if row.get('packing', {}).get('recordedAt')]
    return [dict(at=row['taping']['at'], count=1, outcome=row['outcome'], shiftStartedAt=row['taping']['shiftStartedAt'])
            for row in state['boxes'] if 'taping' in row]


def periods(rows, now):
    return [(row['start'], row.get('end', now)) for row in rows]


def intervention_rows(faults):
    for fault in faults:
        intervention = fault.get('intervention', {})
        for row in intervention.get('intervals', []):
            yield {**row, 'reason': fault['text']}
        if intervention.get('active'):
            yield {**intervention['active'], 'reason': fault['text']}


def taping_activity(state, now):
    runs, stops = [], []
    for box in state['boxes']:
        result = box.get('taping')
        if result:
            runs.extend(result['runs'])
            stops.extend(result['stops'])
    box = state['activeBox']
    if box:
        runs.extend(box.get('monitorRuns', []))
        stops.extend(box.get('monitorStops', []))
        if box.get('monitorPause'):
            stops.append(box['monitorPause'])
        if not box['paused']:
            runs.append([box['since'], now])
    return runs, stops


def station_status(state, station, maintenance, ongoing):
    if any('end' not in row for row in maintenance):
        return 'maintenance'
    if station not in state['shifts']:
        return 'stopped'
    if station == 'bantlama':
        box = state['activeBox']
        return 'idle' if not box else 'paused' if box['paused'] else 'running'
    if station == 'tekniker':
        return 'running' if ongoing else 'idle'
    if station == 'paketleme' and state['carton']['stage'] in {'parked', 'sealed'}:
        return 'paused' if state['carton']['stage'] == 'parked' else 'stopped'
    return 'unmeasured'


def operator_history(shifts, day_records, activity, start, now, measured):
    workers = []
    for shift in reversed(shifts):
        began = shift['startedAt']
        ended = shift.get('endedAt', now)
        if (shift.get('endedAt') is not None and ended <= start) or began > now:
            continue
        run, stopped, maintenance = activity
        windows = [clip(window, max(start, began), ended) for window in (run, stopped, maintenance)]
        used, downtime, servicing = windows
        active_ms = union_ms(used + downtime + servicing) - union_ms(downtime + servicing) if measured else None
        count = sum(row['count'] for row in day_records if row.get('shiftStartedAt') == began)
        workers.append({'operator': shift['operator'], 'start': began, 'end': shift.get('endedAt'),
                        'activeMs': active_ms if shift.get('observed') or active_ms else None,
                        'count': count if shift.get('observed') or count else None})
    return workers


def technician_tasks(faults, start, now):
    tasks = []
    for fault in faults:
        service = fault.get('intervention', {})
        reported = fault.get('reportedAt', service.get('acceptedAt'))
        completed = service.get('completion', {}).get('at')
        if (reported is None and completed is None) or (completed is not None and completed < start):
            continue
        spans = list(intervention_rows([fault]))
        duration = union_ms(clip(periods(spans, now), start, now)) if spans else None
        tasks.append({'id': fault['id'], 'station': fault['station'], 'text': fault['text'], 'kind': fault['kind'],
                      'status': fault['status'], 'active': bool(service.get('active')), 'activeMs': duration})
    return tasks


def station_metrics(state, station, start, now):
    records = [row for row in production_records(state, station) if start <= row['at'] <= now]
    total = sum(row['count'] for row in records)
    outcomes = {'bantlama': ('good', 'scrap', 'rework', 'allowed'), 'giyotin': ('good', 'scrap')}.get(station, ())
    counts = {outcome: sum(row['count'] for row in records if row.get('outcome') == outcome) for outcome in outcomes}
    hourly = [0] * 24
    for row in records:
        hourly[local_time(row['at']).hour] += row['count']

    shift = state['shifts'].get(station)
    shifts = list(state.get('shiftHistory', {}).get(station, []))
    if shift:
        shifts.append(shift)
    staffed = clip([(row['startedAt'], row.get('endedAt', now)) for row in shifts], start, now)
    observed = clip([(row['startedAt'], row.get('endedAt', now)) for row in shifts if row.get('observed')], start, now)

    faults = state['faults']
    maintenance = list(intervention_rows(row for row in faults if row['kind'] == 'fault' and row['station'] == STATIONS[station]))
    activity, stops, interventions = [], [], []
    if station == 'bantlama':
        activity, stops = taping_activity(state, now)
    elif station == 'paketleme':
        stops = list(state.get('packingStops', []))
        if state['carton'].get('monitorPause'):
            stops.append(state['carton']['monitorPause'])
    elif station == 'tekniker':
        interventions = list(intervention_rows(faults))
        activity = periods(interventions, now)

    run = clip(activity, start, now)
    downtime = clip(periods(stops, now), start, now)
    if station == 'paketleme':
        downtime = [part for left, right in staffed for part in clip(downtime, left, right)]
    servicing = clip(periods(maintenance, now), start, now)
    measured = station in {'bantlama', 'tekniker'}
    covered = union_ms(run + downtime + servicing)
    active_ms = covered - union_ms(downtime + servicing)
    stop_ms = union_ms(downtime + servicing) - union_ms(servicing)
    idle_ms = sum((right - left) - union_ms(clip(run + downtime + servicing, left, right)) for left, right in observed)
    stop_reasons = [row['reason'] for row in stops + maintenance if row['start'] <= now and row.get('end', now) > start]
    working = any('end' not in row for row in interventions)
    status = station_status(state, station, maintenance, working)
    if status == 'paused' and not stop_reasons:
        reason = (state['activeBox'] or {}).get('pauseReason') if station == 'bantlama' else state['carton'].get('reason')
        if reason:
            stop_reasons.append(reason)

    metrics = {
        'status': status, 'total': total, 'quality': counts, 'hourly': hourly,
        'work': {'activeMs': active_ms if (measured and (observed or run)) else None,
                 'stoppedMs': stop_ms if downtime or (station == 'bantlama' and observed) else None,
                 'maintenanceMs': union_ms(servicing) if servicing else None,
                 'idleMs': idle_ms if measured and observed else None,
                 'stopCount': len(stop_reasons) if stop_reasons or (station == 'bantlama' and observed) else None,
                 'reasons': list(dict.fromkeys(stop_reasons))},
        'workers': operator_history(shifts, records, (run, downtime, servicing), start, now, measured),
    }
    if station == 'tekniker':
        tasks = technician_tasks(faults, start, now)
        metrics.update(tasks=tasks, ongoing=sum(row['status'] == 'accepted' for row in tasks),
                       interventions=sum(start <= row.get('intervention', {}).get('acceptedAt', -1) <= now for row in faults))
    return metrics


def monitoring_snapshot(state, *, now=None):
    now = int(time() * 1000) if now is None else now
    midnight = local_time(now).replace(hour=0, minute=0, second=0, microsecond=0)
    start = int(midnight.timestamp() * 1000)
    return {
        'date': midnight.date().isoformat(), 'hour': local_time(now).hour,
        'stations': {station: station_metrics(state, station, start, now) for station in MONITORED_STATIONS},
    }

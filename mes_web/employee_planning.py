"""İş emri planı ve İstanbul gününe göre günlük üretim özeti."""
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone

from .employee_rules import require

LOCAL_TIME = timezone(timedelta(hours=3))
QUALITIES = ('good', 'scrap', 'rework')
PLANNING_ACTIONS = frozenset({'order-plan', 'daily-target'})


def local_time(ms):
    return datetime.fromtimestamp(ms / 1000, LOCAL_TIME)


def planned_day(action, today):
    value = action.get('day')
    try:
        day = date.fromisoformat(value)
    except (TypeError, ValueError):
        day = None
    require(day is not None and day.isoformat() == value, 'Geçerli bir üretim günü seç.')
    require(value >= today, 'Geçmiş günün hedefi ve iş emri planı korunur.')
    return day


def apply_planning(state, action, now):
    today = local_time(now).date().isoformat()
    day = planned_day(action, today)
    key = day.isoformat()
    if action['type'] == 'daily-target':
        quantity = action.get('quantity')
        require('quantity' in action and (quantity is None or type(quantity) is int and 0 <= quantity <= 1000000),
                'Hedef 0 ile 1.000.000 arasında tam sayı olmalı.')
        targets = state.setdefault('dailyTargets', {})
        if quantity is None:
            targets.pop(key, None)
        else:
            targets[key] = quantity
        return

    order = next((o for o in state['orders'] if o['id'] == action.get('orderId') and not o.get('closedAt')), None)
    require(order, 'Planlanacak açık iş emri bulunamadı.')
    confirmed = [item['exitedAt'] for item in state['items']
                 if item['orderId'] == order['id'] and item['quality'] == 'good'
                 and item.get('exitedAt') is not None and item['exitedAt'] <= now]
    target = sum(order['requirements'].values())
    require(len(confirmed) < target, 'Bu emrin sağlam kutu hedefi tamamlanmış.')
    start = int(datetime.combine(day, time.min, LOCAL_TIME).timestamp() * 1000)
    quantity = target - sum(at < start for at in confirmed)
    previous = [plan for plan in order.get('productionPlan', []) if plan['day'] < today]
    order['productionPlan'] = [*previous, {'day': key, 'quantity': quantity}]


def quality_counts(state, now, days, planned_orders):
    changes = defaultdict(list)
    for change in reversed(state['qualityChanges']):
        if change['at'] <= now:
            changes[change['itemId']].append(change)
    for item in state['items']:
        history = sorted(changes.get(item['id'], ()), key=lambda row: row['at'])
        quality = history[0]['from'] if history else item['quality']
        at = item.get('exitedAt') if quality == 'good' else item.get('completedAt') or item.get('exitedAt')
        if at is None and history:
            at = history[0]['at']
        if at is None or at > now:
            continue
        moment = local_time(at)
        day = moment.date()
        for change in history:
            if local_time(change['at']).date() <= day:
                quality = change['to']
        if quality not in QUALITIES:
            continue
        key = day.isoformat()
        record = days[key]
        record[quality] += 1
        if quality == 'good' and (key, item['orderId']) in planned_orders:
            record['plannedGood'] += 1
        bucket = record['hours'].setdefault(str(moment.hour), {})
        bucket[quality] = bucket.get(quality, 0) + 1


def planning_snapshot(state, now):
    today = local_time(now).date().isoformat()
    days = defaultdict(lambda: {'automatic':None, 'manual':None, 'good':0, 'plannedGood':0,
                                'scrap':0, 'rework':0, 'closed':0, 'hours':{}})
    confirmed = defaultdict(int)
    for item in state['items']:
        if item['quality'] == 'good' and item.get('exitedAt') is not None and item['exitedAt'] <= now:
            confirmed[item['orderId']] += 1
    pending, planned, planned_orders = [], [], set()
    for order in state['orders']:
        plans = order.get('productionPlan', [])
        for plan in plans:
            planned_orders.add((plan['day'], order['id']))
            record = days[plan['day']]
            record['automatic'] = (record['automatic'] or 0) + plan['quantity']
        closed = order.get('closedAt')
        if closed is not None and closed <= now:
            days[local_time(closed).date().isoformat()]['closed'] += 1
        remaining = sum(order['requirements'].values()) - confirmed[order['id']]
        if closed or remaining <= 0:
            continue
        latest = plans[-1]['day'] if plans else None
        row = {'id':order['id'], 'remaining':remaining, 'day':latest}
        (planned if latest and latest >= today else pending).append(row)
    for day, quantity in state.get('dailyTargets', {}).items():
        days[day]['manual'] = quantity
    quality_counts(state, now, days, planned_orders)
    return {'today':today, 'days':dict(days), 'pending':pending, 'planned':planned}

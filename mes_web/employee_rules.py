"""İstasyon iş akışında paylaşılan renk, adım ve sıra kuralları."""


class StationError(ValueError):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


def require(condition, message, status=422):
    if not condition:
        raise StationError(message, status)



COLORS = {'red': 'Kırmızı', 'yellow': 'Sarı', 'blue': 'Mavi'}
STEPS = ['Kutuyu al', 'Tezgâha yerleştir', 'Üstünü bantla', 'Etrafını tek seferde bantla', 'Kontrol et']


def next_id(state, prefix='EV'):
    value = f"{prefix}-{state['nextId']:06d}"
    state['nextId'] += 1
    return value


def remaining(state, order_id, color):
    order = next((o for o in state['orders'] if o['id'] == order_id), None)
    if not order:
        return 0
    reserved = sum(i['orderId'] == order_id and i['color'] == color and i['quality'] == 'good' for i in state['items'])
    box = state.get('activeBox')
    if box and box['orderId'] == order_id and box['color'] == color:
        reserved += 1
    return max(0, order['requirements'].get(color, 0) - reserved)


def event(state, now, text, kind='production'):
    state['events'].insert(0, {'at': now, 'text': text, 'kind': kind})
    state['events'] = state['events'][:300]


def record_demo_exit(state, item, now):
    item.update(stage='exited', exitedAt=now)
    state['logs'].insert(0, {'id': next_id(state, 'LOG'), 'at': now, 'color': item['color'],
                            'sensor': item['color'], 'itemId': item['id'], 'orderId': item['orderId'],
                            'result': 'matched', 'source': 'demo'})


def advance_queue(state, now):
    instruction = state.get('instruction')
    if instruction:
        current_done = all(remaining(state, state['activeOrder'], c) == 0 for c in COLORS)
        if instruction.get('acknowledgedAt') and not state['activeBox'] and (instruction['mode'] == 'immediate' or current_done):
            state['instructionHistory'].insert(0, {**instruction, 'appliedAt': now, 'fromOrder': state['activeOrder']})
            state['activeOrder'] = instruction['orderId']
            state['instruction'] = None
        else:
            return
    if state['activeBox'] or any(remaining(state, state['activeOrder'], c) for c in COLORS):
        return
    candidates = sorted((o for o in state['orders'] if not o.get('closedAt') and any(remaining(state, o['id'], c) for c in COLORS)), key=lambda o: o['rank'])
    state['activeOrder'] = candidates[0]['id'] if candidates else None

"""Bantlama, öncelik ve paketleme kuralları; arayüzden bağımsız."""
from .employee_rules import require
from .employee_rules import COLORS, STEPS, advance_queue, event, next_id, remaining
from .employee_planning import PLANNING_ACTIONS, apply_planning

FLOOR = {'claim-box', 'start-box', 'step', 'pause-box', 'resume-box', 'finish-box', 'ack', 'material', 'fault', 'shift', 'activity-start', 'activity-end'}
PACKING = {'pack', 'seal', 'park', 'unpark', 'fault'}
ACTIONS = {'taping': FLOOR, 'packing': PACKING | {'shift'}, 'technician': {'resolve', 'fault', 'shift'}, 'engineer': {'instruction', 'cancel-instruction', 'restock', 'reorder'} | PLANNING_ACTIONS}


def text(value, limit=500):
    return value.strip()[:limit] if isinstance(value, str) else ''


def apply_action(state, action, actor, now):
    kind, role = action.get('type'), actor.get('role')
    allowed = kind in ACTIONS.get(role, ())
    require(allowed and role != 'management', 'Bu işlem için yetkiniz yok.', 403)
    s = state
    box = s.get('activeBox')
    station_shifts = s.get('stationShifts', {})
    shift = station_shifts.get(role, {}) if role in {'packing', 'technician'} else s['shift']
    named_shift = shift.get('active') and shift.get('operatorAccountId')
    paired = actor.get('pairedTablet')
    transferable_box = role == 'taping' and box and (box.get('handoverRequired') or paired and box.get('operatorId') != actor['id'])
    operator_name = shift['operator'] if named_shift and role in {'taping','packing','technician'} else actor.get('name', '')
    if paired and kind not in {'shift','activity-end'}:
        require(named_shift, 'Önce ad soyadını girip vardiyayı başlat.', 409)
    if kind in {'step', 'pause-box', 'resume-box', 'finish-box'}:
        require(box, 'Açık kutu yok.')
        require(role in {'admin', 'engineer'} or box.get('operatorId') == actor['id'], 'Kutu başka operatöre ait.', 403)
    if kind in PLANNING_ACTIONS:
        require(role=='engineer', 'Üretim planını mühendis kendi panelinden düzenler.', 403)
        apply_planning(s, action, now)
    elif kind == 'claim-box':
        require(transferable_box, 'Devralınmayı bekleyen kutu yok.',403)
        box.setdefault('handoverHistory',[]).append({'at':now,'fromId':box.get('operatorId'),'fromName':box.get('operator'),'toId':actor['id'],'toName':operator_name,'reason':'Genel panelden başlatılmış eski işlemin istasyon operatörüne devri'})
        box.update(operatorId=actor['id'],operator=operator_name,handoverRequired=False)
        event(s,now,f"{box['id']} kutusunu {operator_name} mevcut adımlarıyla devraldı.")
    elif kind == 'start-box':
        color = action.get('color')
        require(s['shift']['active'] and not box and not s['activity'], 'Vardiyayı başlatın ve açık işlemi bitirin.')
        require(isinstance(color,str) and color in COLORS and s['activeOrder'], 'Aktif iş emri ve bant rengi gerekli.')
        require(s['tape'][color] != 'empty', 'Bu renk bant tükenmiş.')
        require(remaining(s, s['activeOrder'], color) > 0, 'Bu rengin hedef miktarı ayrılmış veya tamamlanmış.')
        s['activeBox'] = {'id': next_id(s, 'KT'), 'orderId': s['activeOrder'], 'color': color,
                          'steps': [False] * len(STEPS), 'startedAt': now, 'since': now,
                          'activeMs': 0, 'pausedMs': 0, 'paused': False,
                          'operator': operator_name, 'operatorId': actor['id']}
    elif kind == 'step':
        index = action.get('index')
        require(type(index) is int and 0 <= index < len(STEPS), 'İşlem adımı geçersiz.')
        require(not box['paused'], 'Önce kutu işlemine devam edin.')
        require(index == next((i for i, done in enumerate(box['steps']) if not done), -1), 'Sıradaki işlem adımını tamamla.')
        box['steps'][index] = True
    elif kind in {'pause-box', 'resume-box'}:
        pause = kind == 'pause-box'
        require(box['paused'] != pause, 'Kutu zaten bu durumda.')
        if pause:
            require(text(action.get('reason')), 'Duraklama nedenini yazın.')
        key = 'pausedMs' if box['paused'] else 'activeMs'
        box[key] += max(0, now - box['since'])
        box.update(paused=pause, since=now)
        if pause:
            box['pauseReason'] = text(action['reason'])
            box.setdefault('pauseHistory', []).append({'at': now, 'reason': box['pauseReason']})
        elif box.get('pauseHistory') and box['pauseHistory'][-1].get('end') is None:
            box['pauseHistory'][-1]['end'] = now
    elif kind == 'finish-box':
        outcome = action.get('outcome')
        require(isinstance(outcome,str) and outcome in {'good', 'scrap', 'rework'} and not box['paused'], 'Sonucu seçin ve duraklamayı bitirin.')
        require(outcome != 'good' or all(box['steps']), 'Sağlam ürün için bütün işlem kutucuklarını tamamlayın.')
        require(outcome == 'good' or text(action.get('reason')), 'Kalite kararının nedenini yazın.')
        item = {**box, 'quality': outcome, 'stage': 'transit' if outcome == 'good' else outcome,
                'deliveredAt': now if outcome == 'good' else None, 'completedAt': now,
                'activeMs': box['activeMs'] + max(0, now - box['since']), 'reason': text(action.get('reason'))}
        s['items'].append(item)
        s['activeBox'] = None
        event(s, now, f"{item['id']} · {item['orderId']} · {COLORS[item['color']]}: {'konveyöre teslim edildi' if outcome == 'good' else outcome}.")
        advance_queue(s, now)
    elif kind == 'instruction':
        order_id, mode = action.get('orderId'), action.get('mode')
        order = next((o for o in s['orders'] if o['id'] == order_id), None)
        require(not s['instruction'], 'Bekleyen talimatı önce uygulayın veya iptal edin.')
        require(order and not order.get('closedAt') and order_id != s['activeOrder'] and any(remaining(s, order_id, c) for c in COLORS), 'Başka bir açık iş emri seçin.')
        require(isinstance(mode,str) and mode in {'immediate', 'after-order'}, 'Geçiş biçimi geçersiz.')
        s['instruction'] = {'id': next_id(s), 'orderId': order_id, 'mode': mode, 'requestedAt': now, 'acknowledgedAt': None, 'sender': actor.get('name')}
        event(s, now, f'{order_id} için öncelik talimatı gönderildi.', 'warning')
    elif kind == 'ack':
        require(s['instruction'] and not s['instruction'].get('acknowledgedAt'), 'Onay bekleyen talimat yok.')
        s['instruction']['acknowledgedAt'] = now
        advance_queue(s, now)
    elif kind == 'cancel-instruction':
        require(s['instruction'], 'Bekleyen talimat yok.')
        s['instructionHistory'].insert(0, {**s['instruction'], 'cancelledAt': now})
        s['instruction'] = None
        advance_queue(s, now)
    elif kind == 'pack':
        item = next((i for i in s['items'] if i['id'] == action.get('itemId')), None)
        require(item and item['stage'] == 'exited' and item['quality'] == 'good' and not any(order.get('parkedAt') for order in s['orders'] if order['id'] == item['orderId']), 'Paketlemeye hazır sağlam kutu bulunamadı.')
        item.update(stage='packed', packedAt=now, packedBy=operator_name, packedById=actor['id'])
    elif kind == 'seal':
        order = next((o for o in s['orders'] if o['id'] == action.get('orderId')), None)
        require(order and not order.get('closedAt'), 'Açık iş emri bulunamadı.')
        require(all(sum(i['orderId'] == order['id'] and i['color'] == c and i['stage'] == 'packed' and i['quality'] == 'good' for i in s['items']) == order['requirements'].get(c, 0) for c in COLORS), 'Bütün hedef sağlam ürünler kolide olmalı.')
        order['closedAt'] = now
        order['closedBy'] = operator_name
        event(s, now, f"{order['id']} müşteri kolisi tamamlandı.", 'success')
    elif kind in {'park', 'unpark'}:
        order = next((o for o in s['orders'] if o['id'] == action.get('orderId')), None)
        require(order and not order.get('closedAt'), 'Açık iş emri bulunamadı.')
        if kind == 'park':
            require(text(action.get('reason')), 'Eksik bırakma nedenini yazın.')
            order.update(parkedAt=now, parkReason=text(action['reason']))
        else:
            require(order.get('parkedAt'), 'Bu koli ayrılmamış.')
            order.setdefault('parkHistory', []).append({'at': order['parkedAt'], 'end': now, 'reason': order.get('parkReason')})
            order['parkedAt'] = None
    elif kind == 'material':
        color, level = action.get('color'), action.get('level')
        require(isinstance(color,str) and color in COLORS and isinstance(level,str) and level in {'low', 'empty'} and text(action.get('reason')), 'Bant rengi, durum ve kısa neden gerekli.')
        s['tape'][color] = level
        s['alerts'].insert(0, {'id': next_id(s, 'AL'), 'kind': 'material', 'title': f"{COLORS[color]} bant {'bitti' if level == 'empty' else 'azalıyor'}", 'reason': text(action['reason']), 'color': color, 'level': level, 'station': 'BNT-01', 'orderId': s['activeOrder'], 'at': now, 'resolved': False})
    elif kind == 'restock':
        color = action.get('color')
        require(isinstance(color,str) and color in COLORS, 'Bant rengini seçin.')
        s['tape'][color] = 'ok'
        for alert in s['alerts']:
            if alert.get('kind') == 'material' and alert.get('color') == color:
                alert.update(resolved=True, resolvedAt=now)
    elif kind == 'fault':
        require(text(action.get('reason')), 'Arıza açıklamasını yazın.')
        default_station = {'taping':'BNT-01','packing':'PKT-01'}.get(role)
        order_id = action.get('orderId') if role=='packing' else s['activeOrder'] if role=='taping' else None
        if order_id and not any(o['id']==order_id and not o.get('closedAt') for o in s['orders']):
            order_id = None
        s['alerts'].insert(0, {'id': next_id(s, 'AL'), 'kind': 'fault', 'title': 'İstasyon arıza bildirimi', 'reason': text(action['reason']), 'station': actor.get('stationId') or default_station, 'orderId': order_id, 'at': now, 'resolved': False, 'reportedBy': operator_name})
        s['lineStops'].append({'id': next_id(s, 'STOP'), 'start': now, 'end': None, 'reason': text(action['reason'])})
    elif kind == 'resolve':
        alert = next((a for a in s['alerts'] if a['id'] == action.get('id') and not a.get('resolved')), None)
        require(alert and (role!='technician' or alert['kind']=='fault'), 'Açık arıza bulunamadı.')
        alert.update(resolved=True, resolvedAt=now, resolvedBy=operator_name)
        if alert['kind'] == 'fault' and not any(a['kind'] == 'fault' and not a.get('resolved') for a in s['alerts']):
            for stop in s['lineStops']:
                if stop.get('end') is None:
                    stop['end'] = now
    elif kind == 'shift':
        title = {'packing':'Paketleme','technician':'Tekniker'}.get(role,'Bantlama')
        operation = action.get('operation')
        require(operation in ('start', 'end'), 'Vardiya işlemini seçin.')
        if role not in {'packing','technician'}:
            can_transfer = operation == 'start' and paired and transferable_box and not named_shift
            require((not box or can_transfer) and not s['activity'], 'Önce açık kutu veya faaliyeti bitirin.')
        if operation == 'end':
            require(shift.get('active'), 'Açık vardiya yok.')
            shift.update(active=False, endedAt=now)
            event(s, now, f"{title} vardiyası bitti. Çalışan: {shift['operator']}.")
        else:
            require(not named_shift, 'Önce açık vardiyayı bitirin.')
            worker = text(action.get('operator'), 81)
            require(1 <= len(worker) <= 80, 'Çalışanın ad soyadını girin (en fazla 80 karakter).')
            started = {'active': True, 'operator': worker, 'operatorAccountId': actor['id'],
                       'startedAt': now, 'endedAt': None}
            if role in {'packing','technician'}:
                s.setdefault('stationShifts', {})[role] = started
            else:
                s['shift'] = started
            event(s, now, f'{title} vardiyası başladı. Çalışan: {worker}.')
    elif kind == 'activity-start':
        require(not box and not s['activity'] and s['shift']['active'], 'Vardiyayı ve açık işlemleri kontrol edin.')
        s['activity'] = {'id': next_id(s, 'ACT'), 'name': text(action.get('name'), 80) or 'Tezgâh temizliği', 'startedAt': now, 'expected': s['settings']['cleaningMinutes'], 'operator': operator_name}
    elif kind == 'activity-end':
        activity = s['activity']
        require(activity, 'Açık faaliyet yok.')
        minutes = round(max(0, now - activity['startedAt']) / 60000, 2)
        require(minutes <= activity['expected'] or text(action.get('reason')), 'Standart süre aşıldı; kısa neden yazın.')
        s['activities'].insert(0, {**activity, 'endedAt': now, 'minutes': minutes, 'reason': text(action.get('reason'))})
        s['activity'] = None
    elif kind == 'reorder':
        ids = action.get('ids') or action.get('orderedIds')
        current = {order['id']: order for order in s['orders'] if not order.get('closedAt')}
        require(isinstance(ids, list) and all(isinstance(order_id, str) for order_id in ids)
                and len(ids) == len(current) and set(ids) == current.keys(), 'Sıra bütün açık iş emirlerini bir kez içermeli.')
        for rank, order_id in enumerate(ids, 1):
            current[order_id]['rank'] = rank
    return s

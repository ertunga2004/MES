"""Separate the tablet, staff, and legacy MES access surfaces."""

import base64
from collections import deque
import hashlib
import hmac
import json
import os
import secrets
from threading import Lock
import time
from urllib.parse import urlencode

from fastapi import HTTPException
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse, RedirectResponse


STATIONS = {
    'bantlama': 'Bantlama', 'paketleme': 'Paketleme', 'giyotin': 'Giyotin',
    'kaplama': 'Kaplama', 'konveyor': 'Konveyör', 'tekniker': 'Tekniker',
    'kalite': 'Kalite', 'malzeme': 'Malzeme',
}
STATION_PORTS = {
    'bantlama': 18781, 'paketleme': 18782, 'giyotin': 18783, 'kaplama': 18784,
    'konveyor': 18785, 'tekniker': 18786, 'kalite': 18787, 'malzeme': 18788,
}
PORT_STATIONS = {port: station for station, port in STATION_PORTS.items()}
STAFF = {'admin', 'engineer', 'supervisor'}
DESIGNERS = {'admin', 'engineer'}
LOOPBACK = {'127.0.0.1', '::1', 'localhost'}
COOKIE = 'mes_workspace'
TABLET_ASSETS = {
    '/static/kiosk.css', '/static/styles.css', '/static/atolye-tablets.css',
    '/static/atolye-tablets.mjs', '/static/atolye-tablet-state.mjs',
    '/static/atolye-onizleme-core.js', '/static/atolye-onizleme-data.js', '/static/mes-workspace-auth.mjs',
}


def workspace_url(tab):
    return '/?' + urlencode({'module': 'konveyor_main', 'tab': tab}, safe='/')


def listener_station(connection):
    server = connection.scope.get('server')
    return PORT_STATIONS.get(server[1]) if server else None


def requested_station(connection):
    path = connection.url.path
    if path == '/':
        tab = connection.query_params.get('tab', '')
        return tab.removeprefix('operations/') if tab.startswith('operations/') else None
    if path.startswith('/operations/'):
        return path.removeprefix('/operations/')
    if path == '/tablet-ekrani':
        return connection.query_params.get('istasyon')
    return None


def encode(data):
    return base64.urlsafe_b64encode(data).decode('ascii').rstrip('=')


def decode(data):
    return base64.urlsafe_b64decode(data + '=' * (-len(data) % 4))


class WorkspaceAccess:
    def __init__(self, engineer_password):
        self.users = {
            'admin': ('admin', os.environ.get('MES_WEB_WORKSPACE_ADMIN_PASSWORD', '')),
            'muhendis': ('engineer', engineer_password),
            'sef': ('supervisor', os.environ.get('MES_WEB_WORKSPACE_SUPERVISOR_PASSWORD', '')),
        }
        mode = os.environ.get('MES_WEB_WORKSPACE_ACCESS_ENABLED')
        configured_staff = bool(self.users['admin'][1] or self.users['sef'][1])
        self.preview = os.environ.get('MES_WEB_WORKSPACE_LOCAL_PREVIEW') == '1' and mode != '1' and not configured_staff
        self.secured = configured_staff or (mode != '0' and not self.preview)
        secret = os.environ.get('MES_WEB_WORKSPACE_SESSION_SECRET')
        self.secret = secret.encode() if secret else secrets.token_bytes(32)
        self.invites = {}
        self.attempts = {}
        self.lock = Lock()

    def token(self, role, station='', lifetime=8 * 60 * 60):
        body = encode(json.dumps({'role': role, 'bound_station_id': station, 'exp': int(time.time()) + lifetime},
                                 separators=(',', ':')).encode())
        signature = encode(hmac.digest(self.secret, body.encode(), 'sha256'))
        return f'{body}.{signature}'

    def identity(self, connection):
        raw = connection.cookies.get(COOKIE)
        if raw:
            try:
                body, signature = raw.split('.', 1)
                if hmac.compare_digest(hmac.digest(self.secret, body.encode(), 'sha256'), decode(signature)):
                    claims = json.loads(decode(body))
                    if claims['exp'] > time.time():
                        return claims
                # An expired tablet cookie must fail closed even on the preview host.
                return {'role': 'invalid', 'bound_station_id': ''}
            except (ValueError, KeyError, TypeError):
                return {'role': 'invalid', 'bound_station_id': ''}
        if self.preview and connection.client and connection.client.host in LOOPBACK and connection.url.hostname in LOOPBACK:
            return {'role': 'admin', 'bound_station_id': ''}
        return {'role': 'anonymous', 'bound_station_id': ''}

    def authorize(self, connection, roles):
        identity = self.identity(connection)
        if identity['role'] not in roles:
            raise HTTPException(401 if identity['role'] in {'anonymous', 'invalid'} else 403, 'Bu çalışma alanına erişim izniniz yok.')
        return identity

    def tablet(self, connection, station):
        if station not in STATIONS:
            raise HTTPException(404, 'İstasyon bulunamadı.')
        identity = self.authorize(connection, {'admin', 'tablet'})
        if identity['role'] == 'tablet' and identity['bound_station_id'] != station:
            raise HTTPException(403, 'Tablet başka bir istasyona bağlı.')
        return identity

    def attempt(self, connection, purpose):
        peer = connection.client.host if connection.client else ''
        now = time.monotonic()
        with self.lock:
            self.attempts = {key: entries for key, entries in self.attempts.items() if entries[-1] > now - 60}
            entries = self.attempts.setdefault((purpose, peer), deque())
            while entries and entries[0] <= now - 60:
                entries.popleft()
            if len(entries) >= 12:
                raise HTTPException(429, 'Çok fazla deneme. Bir dakika sonra tekrar deneyin.')
            entries.append(now)

    def login(self, connection, username, password):
        self.attempt(connection, 'login')
        role, expected = self.users.get(username, ('', ''))
        if not expected or not hmac.compare_digest(expected.encode(), password.encode()):
            raise HTTPException(401, 'Kullanıcı adı veya parola geçersiz.')
        return self.token(role)

    def invite(self, station):
        if station not in STATIONS:
            raise HTTPException(404, 'İstasyon bulunamadı.')
        code = secrets.token_urlsafe(18)
        now = time.monotonic()
        with self.lock:
            self.invites = {key: value for key, value in self.invites.items() if value[1] > now and value[0] != station}
            self.invites[hashlib.sha256(code.encode()).digest()] = (station, now + 600)
        return code

    def pair(self, connection, code):
        self.attempt(connection, 'pair')
        expected_station = listener_station(connection)
        key = hashlib.sha256(code.strip().encode()).digest()
        with self.lock:
            row = self.invites.get(key)
            if not row or row[1] <= time.monotonic():
                raise HTTPException(400, 'Eşleştirme kodu geçersiz veya süresi dolmuş.')
            station = row[0]
            if expected_station and station != expected_station:
                raise HTTPException(403, 'Bu kod başka bir istasyon portuna ait.')
            del self.invites[key]
        return station, self.token('tablet', station, lifetime=30 * 24 * 60 * 60)

    def set_cookie(self, response, connection, token, lifetime):
        response.set_cookie(COOKIE, token, max_age=lifetime, httponly=True, samesite='strict',
                            secure=connection.url.scheme == 'https', path='/')


class WorkspaceBoundary:
    def __init__(self, app, access):
        self.app = app
        self.access = access

    async def __call__(self, scope, receive, send):
        if scope['type'] not in {'http', 'websocket'}:
            return await self.app(scope, receive, send)
        connection = HTTPConnection(scope)
        identity = self.access.identity(connection)
        role = identity['role']
        path = connection.url.path
        station_port = listener_station(connection)
        if scope['type'] == 'websocket':
            if station_port or role == 'tablet' or (self.access.secured and role not in STAFF):
                return await send({'type': 'websocket.close', 'code': 1008})
            return await self.app(scope, receive, send)

        method = scope['method']
        if station_port:
            if role == 'tablet' and identity['bound_station_id'] != station_port:
                return await JSONResponse({'detail': 'Tablet başka bir istasyona bağlı.'}, status_code=403)(scope, receive, send)
            read_paths = TABLET_ASSETS | {'/tablet-eslestir', '/health', '/favicon.ico'}
            is_station_view = requested_station(connection) == station_port or (path == '/' and not connection.query_params.get('tab'))
            station_api = f'/api/workspace/tablet/{station_port}'
            allowed = (
                method in {'GET', 'HEAD'} and (is_station_view or path in read_paths)
                or method == 'GET' and path == station_api
                or method == 'POST' and path in {f'{station_api}/actions', '/api/workspace/pair'}
            )
            if not allowed:
                return await JSONResponse({'detail': 'Bu port yalnız kendi istasyonuna hizmet verir.'}, status_code=403)(scope, receive, send)
            return await self.app(scope, receive, send)

        if self.access.secured and path.casefold() == '/static/index.html':
            return await JSONResponse({'detail': 'Sayfa bulunamadı.'}, status_code=404)(scope, receive, send)
        station = requested_station(connection)
        if role == 'tablet':
            bound = identity['bound_station_id']
            allowed = (
                method in {'GET', 'HEAD'} and (station == bound or path in TABLET_ASSETS or path == '/favicon.ico')
                or method == 'GET' and path == f'/api/workspace/tablet/{bound}'
                or method == 'POST' and path == f'/api/workspace/tablet/{bound}/actions'
            )
            if not allowed:
                return await JSONResponse({'detail': 'Tablet yalnız kendi istasyonuna erişebilir.'}, status_code=403)(scope, receive, send)
        elif self.access.secured and not (
            path.startswith('/static/') or path in {'/health', '/favicon.ico', '/mes-oturum', '/tablet-eslestir'}
            or path.startswith('/api/workspace/') or station is not None
        ):
            if role not in STAFF:
                response = RedirectResponse('/mes-oturum', status_code=303) if method == 'GET' and path == '/' else JSONResponse({'detail': 'Oturum açın.'}, status_code=401)
                return await response(scope, receive, send)
            if role != 'admin' and method not in {'GET', 'HEAD'} and not path.startswith('/api/kiosk-designs/'):
                return await JSONResponse({'detail': 'Yönetici yetkisi gerekli.'}, status_code=403)(scope, receive, send)
        return await self.app(scope, receive, send)

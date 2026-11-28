"""Routes for the station-bound kiosk, staff dashboard and template designer."""

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from .giyotin_runtime import GiyotinError, GiyotinRuntime
from .kiosk_designer import Section, Step, _clean_design, Design
from .station_access import DESIGNERS, STAFF, STATIONS, STATION_PORTS, WorkspaceAccess, WorkspaceBoundary, listener_station, workspace_url
from .station_workflow import StationWorkflow, require


HEADERS = {'Cache-Control': 'no-store', 'Content-Security-Policy': "frame-ancestors 'none'"}
GIYOTIN_ACTIONS = {
    'giyotin-start': 'Çevrim izni isteniyor.',
    'giyotin-pause': 'İzin kaldırma işlemi başlatıldı.',
    'giyotin-stop': 'İzin kaldırma işlemi başlatıldı.',
    'giyotin-reconcile': 'Çevrim uzlaştırması kaydedildi.',
    'giyotin-calibrate': 'Kalibrasyon onayı bekleniyor.',
    'giyotin-ping': 'Bağlantı sorgusu gönderildi.',
    'giyotin-status': 'Durum sorgusu gönderildi.',
}
GIYOTIN_ERRORS = {
    'offline': 'Canlı ESP32 ve Nano bağlantısını bekleyin.',
    'not_ready': 'Nano yeni işlem için hazır değil.',
    'blocked': 'Açık çevrim, komut veya uzlaştırma tamamlanmalı.',
    'order_or_shift_ended': 'Giyotin vardiyasını açın ve MES’te bir iş emri başlatın.',
    'order_changed': 'Aktif iş emri değişti. Ekranı yenileyin.',
    'target_unavailable': 'Bu iş emri yeni çevrim için uygun değil.',
    'invalid_calibration': 'Kalibrasyon değerleri geçersiz.',
    'invalid_resolution': 'Uzlaştırma seçimi geçersiz veya kayıt değişti.',
    'publish_failed': 'MQTT isteği doğrulanamadı. Cihaz durumunu kontrol edin.',
}


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=256)


class PairCode(BaseModel):
    code: str = Field(min_length=12, max_length=120)


class StationAction(BaseModel):
    action: str = Field(min_length=1, max_length=32)
    fields: dict[str, Any] = Field(default_factory=dict, max_length=48)


class TemplateCard(BaseModel):
    kind: Literal['order', 'instructions', 'steps', 'timer', 'progress', 'result', 'status', 'wip', 'downtime', 'actions', 'material', 'before', 'after', 'extra']
    size: Literal['small', 'medium', 'large', 'full'] = 'full'
    source: Literal['fixed', 'station', 'order'] = 'fixed'
    visible: bool = True
    title: str = Field(default='', max_length=80)
    body: str = Field(default='', max_length=1500)


class TemplateProgress(BaseModel):
    target: int = Field(ge=1, le=1_000_000)
    unit: str = Field(min_length=1, max_length=32)


class TemplateFeatures(BaseModel):
    timer: bool = False
    progress: TemplateProgress | None = None
    result: list[str] | None = Field(default=None, max_length=12)


class TemplateDraft(BaseModel):
    title: str = Field(min_length=1, max_length=60)
    layout: Literal['single', 'double', 'sidebar'] = 'single'
    instructions: str = Field(default='', max_length=1500)
    before: str = Field(default='', max_length=1500)
    after: str = Field(default='', max_length=1500)
    cards: list[TemplateCard] = Field(default_factory=list, max_length=14)
    steps: list[Step] = Field(default_factory=list, max_length=30)
    sections: list[Section] = Field(default_factory=list, max_length=20)
    features: TemplateFeatures = Field(default_factory=TemplateFeatures)


class TemplateChange(BaseModel):
    revision: int = Field(ge=0)
    design: TemplateDraft


class TemplatePublish(BaseModel):
    revision: int = Field(ge=0)


def json_write(request: Request):
    if request.headers.get('content-type', '').partition(';')[0].strip().lower() != 'application/json':
        raise HTTPException(415, 'JSON istek gerekli.')
    origin = request.headers.get('origin')
    if origin is not None and origin != f'{request.url.scheme}://{request.url.netloc}':
        raise HTTPException(403, 'İstek aynı MES adresinden gelmeli.')


class StationWorkspace:
    def __init__(self, app, static_dir, config, oee_manager, publish_giyotin, on_giyotin_production):
        self.static_dir = static_dir
        self.access = WorkspaceAccess(config.kiosk_design_password)
        self.workflow = StationWorkflow()
        self.giyotin = (
            GiyotinRuntime(config, oee_manager, self.giyotin_shift, publish_giyotin, on_production=on_giyotin_production)
            if config.giyotin_protocol4_enabled else None
        )
        app.add_middleware(WorkspaceBoundary, access=self.access)
        router = APIRouter()

        @router.get('/mes-oturum', response_class=HTMLResponse)
        def login_page():
            return self.auth_page('MES oturumu', 'login')

        @router.get('/tablet-eslestir', response_class=HTMLResponse)
        def pair_page():
            return self.auth_page('Tablet eşleştirme', 'pair')

        @router.post('/api/workspace/login', dependencies=[Depends(json_write)])
        def login(payload: Credentials, request: Request):
            token = self.access.login(request, payload.username.strip().lower(), payload.password)
            response = JSONResponse({'path': workspace_url('monitoring')}, headers=HEADERS)
            self.access.set_cookie(response, request, token, 8 * 60 * 60)
            return response

        @router.get('/api/workspace/identity')
        def identity(request: Request):
            return JSONResponse({'role': self.access.identity(request)['role']}, headers=HEADERS)

        @router.post('/api/workspace/pair', dependencies=[Depends(json_write)])
        def pair(payload: PairCode, request: Request):
            station, token = self.access.pair(request, payload.code)
            path = '/' if listener_station(request) else workspace_url(f'operations/{station}')
            response = JSONResponse({'bound_station_id': station, 'path': path}, headers=HEADERS)
            self.access.set_cookie(response, request, token, 30 * 24 * 60 * 60)
            return response

        @router.post('/api/workspace/pair-codes/{station}', dependencies=[Depends(json_write)])
        def pair_code(station: str, request: Request):
            self.access.authorize(request, {'admin'})
            return JSONResponse({'code': self.access.invite(station), 'expires_in': 600,
                                 'pair_path': '/tablet-eslestir', 'station_port': STATION_PORTS[station]}, headers=HEADERS)

        @router.get('/operations/{station}', response_class=HTMLResponse)
        def direct_tablet(station: str, request: Request):
            return self.tablet_page(request, station)

        @router.get('/monitoring', response_class=HTMLResponse)
        def direct_monitor(request: Request):
            return self.monitor_page(request)

        @router.get('/designer')
        def direct_designer(request: Request):
            return self.designer_redirect(request)

        @router.get('/api/workspace/tablet/{station}')
        def tablet_data(station: str, request: Request):
            self.access.tablet(request, station)
            return JSONResponse(self.board(self.workflow.read(), station), headers=HEADERS)

        @router.post('/api/workspace/tablet/{station}/actions', dependencies=[Depends(json_write)])
        def tablet_action(station: str, payload: StationAction, request: Request):
            identity = self.access.tablet(request, station)
            if station == 'giyotin' and self.giyotin is not None:
                message, state = self.giyotin_action(payload, identity)
            else:
                message, state = self.workflow.action(station, payload.action, payload.fields)
            return JSONResponse({'message': message, 'board': self.board(state, station)}, headers=HEADERS)

        @router.get('/api/workspace/monitoring')
        def monitor_data(request: Request):
            identity = self.access.authorize(request, STAFF)
            state = self.workflow.read()
            return JSONResponse({'role': identity['role'], 'revision': state['revision'], 'orders': state['orders'],
                                 'boxes': state['boxes'], 'faults': state['faults'], 'packed': state['packed'],
                                 'stations': {station: self.board(state, station) for station in STATIONS}}, headers=HEADERS)

        @router.get('/api/workspace/templates')
        def templates(request: Request):
            self.access.authorize(request, DESIGNERS)
            return JSONResponse(self.workflow.read()['templates'], headers=HEADERS)

        @router.put('/api/workspace/templates/{station}', dependencies=[Depends(json_write)])
        def save_template(station: str, payload: TemplateChange, request: Request):
            self.access.authorize(request, DESIGNERS)
            require(station in STATIONS, 'İstasyon bulunamadı.', 404)
            require(len({card.kind for card in payload.design.cards}) == len(payload.design.cards), 'Kart türleri benzersiz olmalı.', 422)
            validated = _clean_design(Design(title=payload.design.title, instructions=payload.design.instructions,
                                             timer=payload.design.features.timer, result_options=payload.design.features.result or [],
                                             steps=payload.design.steps, sections=payload.design.sections))
            design = {**payload.design.model_dump(), **validated, 'station': station, 'slug': station}
            design['features']['result'] = validated['result_options'] or None

            def update(state):
                row = state['templates'].setdefault(station, {'revision': 0, 'draft': None, 'published': None})
                require(row['revision'] == payload.revision, 'Taslak değişti. Güncel sürümü açın.')
                row['revision'] += 1
                row['draft'] = design
                return row

            row, _ = self.workflow.edit(update)
            return JSONResponse(row, headers=HEADERS)

        @router.post('/api/workspace/templates/{station}/publish', dependencies=[Depends(json_write)])
        def publish_template(station: str, payload: TemplatePublish, request: Request):
            self.access.authorize(request, DESIGNERS)
            require(station in STATIONS, 'İstasyon bulunamadı.', 404)

            def update(state):
                row = state['templates'].get(station)
                require(row and row['revision'] == payload.revision, 'Güncel taslağı kaydedin.')
                require(row['draft']['steps'], 'Yayınlamak için en az bir adım ekleyin.', 422)
                row['published'] = {'version': row['revision'], 'design': row['draft']}
                return row

            row, _ = self.workflow.edit(update)
            return JSONResponse(row, headers=HEADERS)

        app.include_router(router)

    def giyotin_shift(self):
        return self.workflow.read()['shifts'].get('giyotin')

    def board(self, state, station):
        board = self.workflow.station_board(state, station)
        if station == 'giyotin' and self.giyotin is not None:
            board['protocol4'] = self.giyotin.board(board['shift'])
        return board

    def giyotin_action(self, payload, identity):
        action, fields = payload.action, payload.fields
        require(action != 'cut', 'Kesim adedi Nano çevrim olaylarından kaydedilir.')
        with self.giyotin.lock:
            if action not in GIYOTIN_ACTIONS:
                message, state = self.workflow.action('giyotin', action, fields)
                if action == 'shift-end':
                    self.giyotin.tick()
                return message, state
            if action == 'giyotin-calibrate':
                require(identity['role'] == 'admin', 'Kalibrasyon için yönetici yetkisi gerekli.', 403)
            try:
                self.giyotin.control(action, fields)
            except GiyotinError as exc:
                code = str(exc)
                status = 503 if code in ('offline', 'publish_failed') else 422 if code.startswith('invalid_') else 409
                raise HTTPException(status, GIYOTIN_ERRORS[code]) from exc
            except OSError as exc:
                raise HTTPException(503, GIYOTIN_ERRORS['publish_failed']) from exc
            return GIYOTIN_ACTIONS[action], self.workflow.read()

    def html(self, filename, values):
        content = (self.static_dir.parent / 'templates' / filename).read_text(encoding='utf-8')
        for key, value in values.items():
            content = content.replace('{{' + key + '}}', value)
        return HTMLResponse(content, headers=HEADERS)

    def auth_page(self, title, mode):
        return self.html('mes-workspace-auth.html', {'title': title, 'mode': mode})

    def tablet_page(self, request, station) -> Response:
        require(station in STATIONS, 'İstasyon bulunamadı.', 404)
        if self.access.identity(request)['role'] in {'anonymous', 'invalid'}:
            return RedirectResponse('/tablet-eslestir', status_code=303, headers=HEADERS)
        self.access.tablet(request, station)
        return self.html('atolye-istasyon.html', {'title': STATIONS[station], 'mode': 'tablet', 'station': station})

    def monitor_page(self, request) -> Response:
        if self.access.identity(request)['role'] in {'anonymous', 'invalid'}:
            return RedirectResponse('/mes-oturum', status_code=303, headers=HEADERS)
        self.access.authorize(request, STAFF)
        return self.html('atolye-istasyon.html', {'title': 'Çalışan İzleme', 'mode': 'monitor', 'station': ''})

    def designer_redirect(self, request):
        if self.access.identity(request)['role'] in {'anonymous', 'invalid'}:
            return RedirectResponse('/mes-oturum?alan=designer', status_code=303, headers=HEADERS)
        self.access.authorize(request, DESIGNERS)
        return RedirectResponse('/atolye-onizleme', status_code=307, headers=HEADERS)

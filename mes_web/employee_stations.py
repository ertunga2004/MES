from __future__ import annotations

import hashlib
import json
import re
from secrets import compare_digest
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, StrictInt, StrictStr

from .conveyor_handoff import handoff_view
from .employee_actions import ACTIONS
from .employee_flow import load_flow, now_ms, operate, panel_snapshot
from .employee_rules import StationError, require
from .manual_coating import manual_coating_progress


STATION_PATHS = {
    "/bantlama": "taping", "/paketleme": "packing", "/tekniker": "technician",
    "/teknisyen": "technician", "/muhendis": "engineer", "/mühendis": "engineer",
}
NATIVE_STATIONS = {"cutting", "coating", "conveyor"}
LOOPBACK = {"127.0.0.1", "::1"}
LOCAL_HOSTS = LOOPBACK | {"localhost"}
KIOSK_ASSETS = {"/static/kiosk.css", "/static/station-kiosk.css", "/static/station-kiosk.js",
                "/static/kiosk-cards.js", "/static/kiosk-presets.js", "/static/kiosk-request.js"}
SHORT_SLUG = re.compile(r"[a-z][a-z0-9-]{1,39}")
RESERVED_SHORT_PATHS = {"/kaplama", "/giyotin", "/docs", "/redoc", "/static", "/health", "/api", "/ws",
                        "/istasyon", "/calisan", "/kiosk", "/technician", "/kiosk-tasarla", "/yonetici"}


class ActionRequest(BaseModel):
    id: StrictStr
    revision: StrictInt
    action: dict[str, Any]


def operator_access(request: Request, config) -> None:
    if not request.client:
        raise HTTPException(403, "İstasyon istemcisi bulunamadı.")
    if not config.employee_tablets_enabled and (
        request.client.host not in LOOPBACK or request.url.hostname not in LOCAL_HOSTS
    ):
        raise HTTPException(403, "Bu istasyon yalnızca MES bilgisayarında açık.")
    origin = request.headers.get("origin")
    if origin is not None and origin != f"{request.url.scheme}://{request.url.netloc}":
        raise HTTPException(403, "İstek aynı MES adresinden gelmeli.")


def install_tablet_boundary(app, get_context):
    """When tablet sharing is enabled, reject all network access outside the station surface."""
    class TabletBoundary:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            config, manager = get_context()
            peer = scope.get("client")
            if not config.employee_tablets_enabled or scope["type"] not in {"http", "websocket"} or (
                peer and peer[0] in LOOPBACK
            ):
                await self.app(scope, receive, send)
                return
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
                return
            path = scope["path"]
            method = scope["method"]
            allowed = method in {"GET", "HEAD"} and (
                path in STATION_PATHS or path in KIOSK_ASSETS or path.startswith("/static/employee/")
            )
            employee = re.fullmatch(r"/api/employee-stations/(taping|packing|technician|engineer)(/actions)?", path)
            if employee:
                allowed = (method == "POST") if employee[2] else (method == "GET")
            kiosk = re.fullmatch(r"/(?:api/station-kiosks|istasyon)/([a-z][a-z0-9-]{1,39})(?:/(start|finish|update|pickup))?", path)
            short = path[1:] if method == "GET" and path not in RESERVED_SHORT_PATHS and SHORT_SLUG.fullmatch(path[1:]) else ""
            if kiosk or (short and not allowed):
                slug = kiosk[1] if kiosk else short
                published = manager.read_state()["stationKiosks"].get(slug, {}).get("published")
                if kiosk and path.startswith("/api/station-kiosks/"):
                    allowed = bool(published and method == ("POST" if kiosk[2] else "GET"))
                else:
                    allowed = bool(published and method == "GET" and not (kiosk and kiosk[2]))
            if allowed:
                await self.app(scope, receive, send)
                return
            await JSONResponse({"detail": "Bu adres yalnızca MES bilgisayarından açılabilir."}, status_code=403)(
                scope, receive, send
            )

    app.add_middleware(TabletBoundary)


def native_snapshot(state: dict, config, workspace: str) -> dict:
    progress = manual_coating_progress(state, cutting_enabled=config.cutting_workflow_enabled)
    rows = []
    order = progress["order_id"] if progress else None
    if workspace == "cutting" and progress and (cutting := progress.get("cutting")):
        rows = [("Kesilen bant", f"{cutting['cut_tapes']} / {cutting['target_tapes']}"),
                ("Kaplamaya hazır kutu", cutting["available_boxes"]),
                ("Eşleşmeyi bekleyen bant", cutting["unpaired_tapes"])]
    elif workspace == "coating" and progress:
        rows = [("Kaplanan kutu", f"{progress['completed_qty']} / {progress['target_qty']}"),
                ("Kaplanabilecek kutu", progress["remaining_qty"])]
        if config.conveyor_handoff_enabled:
            handoff = handoff_view(state, progress)
            rows.append(("Konveyöre hazır kutu", handoff["ready_qty"]))
    elif workspace == "conveyor":
        rows = [("Hat vardiyası", "Açık" if state["shift"]["active"] else "Kapalı"),
                ("Hat çıkışı kaydı", state["counts"]["total"])]
    return {"order": order, "rows": rows}


def create_employee_router(static_dir, get_context, require_local):
    router = APIRouter()
    basic = HTTPBasic(auto_error=False, realm="MES Mühendis")
    templates = static_dir.parent / "templates"
    readonly_headers = {"Cache-Control": "no-store", "Content-Security-Policy": "frame-ancestors 'self'"}
    tablet_headers = {"Cache-Control": "no-store", "Content-Security-Policy": "frame-ancestors 'none'"}

    def engineer(credentials):
        password = get_context()[0].kiosk_design_password
        if not password:
            raise HTTPException(503, "Mühendis parolası bu sunucuda tanımlı değil.")
        if not credentials or credentials.username != "muhendis" or not compare_digest(
            credentials.password.encode(), password.encode()
        ):
            raise HTTPException(401, "Mühendis girişi gerekli.",
                                headers={"WWW-Authenticate": 'Basic realm="MES Engineer"'})

    def station(workspace):
        if workspace not in ACTIONS:
            raise HTTPException(404, "İstasyon bulunamadı.")

    def authorize(request, workspace, credentials):
        station(workspace)
        operator_access(request, get_context()[0])
        if workspace == "engineer":
            engineer(credentials)

    def snapshot(workspace, observing):
        config, manager = get_context()
        state = manager.read_state()
        now = now_ms()
        return panel_snapshot(state, load_flow(state, config, now), workspace, now, observing, config)

    def station_page(request: Request, credentials: HTTPBasicCredentials | None = Depends(basic)):
        authorize(request, STATION_PATHS[request.url.path], credentials)
        return FileResponse(templates / "employee-station.html", headers=tablet_headers)

    for path in STATION_PATHS:
        router.add_api_route(path, station_page, methods=["GET"], name=f"employee_{path[1:]}")

    @router.get("/calisan/izle/{workspace}")
    def observer_page(workspace: str, request: Request):
        require_local(request)
        if workspace in NATIVE_STATIONS:
            return FileResponse(templates / "employee-summary.html", headers=readonly_headers)
        station(workspace)
        return FileResponse(templates / "employee-station.html", headers=readonly_headers)

    def observer_state(request: Request):
        require_local(request)
        workspace = request.url.path.rsplit("/", 1)[-1]
        if workspace in NATIVE_STATIONS:
            config, manager = get_context()
            return native_snapshot(manager.read_state(), config, workspace)
        station(workspace)
        return snapshot(workspace, True)

    for workspace in sorted(set(ACTIONS) | NATIVE_STATIONS):
        router.add_api_route(f"/api/employee-observer/{workspace}", observer_state, methods=["GET"],
                             name=f"employee_observer_{workspace}")

    @router.get("/api/employee-stations/{workspace}")
    def station_state(workspace: str, request: Request, credentials: HTTPBasicCredentials | None = Depends(basic)):
        authorize(request, workspace, credentials)
        return snapshot(workspace, False)

    @router.post("/api/employee-stations/{workspace}/actions")
    def mutate(workspace: str, payload: ActionRequest, request: Request,
               credentials: HTTPBasicCredentials | None = Depends(basic)):
        authorize(request, workspace, credentials)
        if request.headers.get("content-type", "").partition(";")[0].strip().lower() != "application/json":
            raise HTTPException(415, "JSON istek gerekli.")
        kind = payload.action.get("type")
        allowed = ACTIONS[workspace] | ({"handoff-confirm", "handoff-close"} if workspace == "taping" else set())
        if not isinstance(kind, str) or kind not in allowed:
            raise HTTPException(403, "Bu işlem bu istasyona ait değil.")
        if payload.revision < 0 or not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", payload.id):
            raise HTTPException(422, "Geçerli istek kimliği ve veri sürümü gerekli.")
        try:
            encoded = json.dumps(payload.action, sort_keys=True, allow_nan=False, ensure_ascii=False)
        except ValueError as exc:
            raise HTTPException(422, "İşlem verisi geçersiz.") from exc
        if len(encoded) > 20_000:
            raise HTTPException(422, "İşlem verisi çok uzun.")
        fingerprint = hashlib.sha256(encoded.encode()).hexdigest()
        config, manager = get_context()
        now = now_ms()

        def edit(state):
            flow = load_flow(state, config, now)
            receipts = flow["receipts"]
            previous = receipts.get(payload.id)
            if previous is not None:
                require(previous == [workspace, fingerprint], "İstek kimliği başka işlemde kullanılmış.", 409)
                return panel_snapshot(state, flow, workspace, now, False, config), False
            require(payload.revision == flow["revision"], "Veri başka ekranda değişti. Güncel ekranla yeniden deneyin.", 409)
            operate(state, flow, config, workspace, payload.action, now)
            flow["revision"] += 1
            receipts[payload.id] = [workspace, fingerprint]
            if len(receipts) > 4_000:
                receipts.pop(next(iter(receipts)))
            state["employeeStations"][flow["mode"]] = {key: value for key, value in flow.items() if key != "orders"}
            return panel_snapshot(state, flow, workspace, now, False, config), True

        try:
            return manager.edit_station_kiosks(edit)
        except StationError as exc:
            raise HTTPException(exc.status, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        except OSError as exc:
            raise HTTPException(500, "İstasyon kaydı yazılamadı.") from exc

    return router

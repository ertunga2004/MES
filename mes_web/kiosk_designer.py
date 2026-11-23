from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from secrets import compare_digest
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field, StrictBool, StrictInt, StrictStr

from .manual_coating import manual_coating_order_key


class Step(BaseModel):
    label: StrictStr
    kind: Literal["check", "text", "number", "choice"]
    required: StrictBool = True
    options: list[StrictStr] = Field(default_factory=list)


class Section(BaseModel):
    title: StrictStr
    body: StrictStr


class Design(BaseModel):
    title: StrictStr
    instructions: StrictStr = ""
    timer: StrictBool = False
    show_target: StrictBool = False
    result_options: list[StrictStr] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)
    sections: list[Section] = Field(default_factory=list)


class Revision(BaseModel):
    revision: StrictInt


class Draft(Revision):
    design: Design


class StartRun(BaseModel):
    run_id: StrictStr
    operator: StrictStr
    order_id: StrictStr
    order_key: StrictStr
    version: StrictInt


class FinishRun(BaseModel):
    run_id: StrictStr
    values: list[Any]
    result: StrictStr = ""


def _text(value: str, limit: int, required: bool = False) -> str:
    value = value.strip()
    if len(value) > limit or (required and not value):
        raise HTTPException(422, "KIOSK_INVALID_TEXT")
    return value


def _options(options: list[str]) -> list[str]:
    values = [_text(label, 60, True) for label in options]
    if not 2 <= len(values) <= 12 or len(set(values)) != len(values):
        raise HTTPException(422, "KIOSK_INVALID_OPTIONS")
    return values


def _clean_design(design: Design) -> dict[str, Any]:
    if len(design.steps) > 30 or len(design.sections) > 20:
        raise HTTPException(422, "KIOSK_DESIGN_LIMIT")
    return {
        "title": _text(design.title, 60, True),
        "instructions": _text(design.instructions, 1500),
        "timer": design.timer, "show_target": design.show_target,
        "result_options": _options(design.result_options) if design.result_options else [],
        "steps": [
            {"label": _text(step.label, 100, True), "kind": step.kind, "required": step.required,
             "options": _options(step.options) if step.kind == "choice" else []}
            for step in design.steps
        ],
        "sections": [{"title": _text(section.title, 80, True), "body": _text(section.body, 1500, True)} for section in design.sections],
    }


def _get_kiosk(state: dict[str, Any], slug: str, published: bool = False) -> dict[str, Any]:
    kiosk = state["stationKiosks"].get(slug)
    if not kiosk or (published and not kiosk["published"]):
        raise HTTPException(404, "KIOSK_NOT_FOUND")
    return kiosk


def _draft_view(slug: str, kiosk: dict[str, Any]) -> dict[str, Any]:
    completed = max(kiosk["completed"].values(), key=lambda run: run["finished_at"], default=None)
    return {"slug": slug, "path": f"/istasyon/{slug}", "draft": kiosk["draft"], "revision": kiosk["revision"],
            "published": kiosk["published"], "published_revision": kiosk["published_revision"],
            "active": kiosk["active"], "last_completed": completed}


def _current_order(state: dict[str, Any]) -> dict[str, Any] | None:
    orders = state["workOrders"]
    order_id = orders["activeOrderId"]
    order = orders["ordersById"].get(order_id)
    if not order or order["status"] != "active":
        return None
    return {"id": order_id, "key": manual_coating_order_key(order), "quantity": order["quantity"], "unit": order["unit"] or "adet"}


def _board(state: dict[str, Any], slug: str) -> dict[str, Any]:
    kiosk = _get_kiosk(state, slug, published=True)
    active = kiosk["active"]
    version = active["version"] if active else kiosk["published"]
    return {"version": version, "design": kiosk["versions"][str(version)], "active": active,
            "order": active["order"] if active else _current_order(state)}


def _completed_values(values: list[Any], design: dict[str, Any], result: str) -> list[Any]:
    if len(values) != len(design["steps"]):
        raise HTTPException(422, "KIOSK_INVALID_STEPS")
    checked = []
    for step, value in zip(design["steps"], values):
        kind = step["kind"]
        if kind == "check":
            valid = type(value) is bool and (value or not step["required"])
        elif value is None:
            valid = not step["required"]
        elif kind == "number":
            valid = type(value) in (int, float) and -1e12 <= value <= 1e12 and math.isfinite(value)
        elif kind == "choice":
            valid = value in step["options"]
        else:
            valid = isinstance(value, str) and len(value) <= 500 and (bool(value.strip()) or not step["required"])
        if not valid:
            raise HTTPException(422, "KIOSK_INVALID_STEP_VALUE")
        checked.append(value.strip() if isinstance(value, str) else value)
    options = design["result_options"]
    if (options and result not in options) or (not options and result):
        raise HTTPException(422, "KIOSK_INVALID_RESULT")
    return checked


def create_kiosk_router(static_dir, get_context, require_local) -> APIRouter:
    router = APIRouter()
    basic = HTTPBasic(auto_error=False, realm="MES Kiosk Tasarla")
    templates = static_dir.parent / "templates"
    html_headers = {"Cache-Control": "no-store", "Content-Security-Policy": "frame-ancestors 'none'"}

    def engineer(request: Request, credentials: HTTPBasicCredentials | None = Depends(basic)) -> None:
        require_local(request)
        password = get_context()[0].kiosk_design_password
        if not password:
            raise HTTPException(503, "KIOSK_DESIGN_PASSWORD_NOT_SET")
        if not credentials or credentials.username != "muhendis" or not compare_digest(credentials.password.encode(), password.encode()):
            raise HTTPException(401, "KIOSK_ENGINEER_REQUIRED", headers={"WWW-Authenticate": 'Basic realm="MES Kiosk Tasarla"'})

    def require_json(request: Request) -> None:
        if request.headers.get("content-type", "").partition(";")[0].strip().lower() != "application/json":
            raise HTTPException(415, "KIOSK_JSON_REQUIRED")

    def read_state() -> dict[str, Any]:
        return get_context()[1].read_state()

    def edit(operation):
        try:
            return get_context()[1].edit_station_kiosks(operation)
        except OSError as exc:
            raise HTTPException(500, "KIOSK_WRITE_FAILED") from exc

    @router.get("/kiosk-tasarla", dependencies=[Depends(engineer)])
    def designer_page() -> FileResponse:
        return FileResponse(templates / "kiosk-designer.html", headers=html_headers)

    @router.get("/api/kiosk-designs", dependencies=[Depends(engineer)])
    def kiosk_designs() -> list[dict[str, Any]]:
        return [_draft_view(slug, kiosk) for slug, kiosk in sorted(read_state()["stationKiosks"].items())]

    @router.put("/api/kiosk-designs/{slug}", dependencies=[Depends(engineer), Depends(require_json)])
    def save_draft(slug: str, payload: Draft) -> dict[str, Any]:
        if not re.fullmatch(r"[a-z][a-z0-9-]{1,39}", slug):
            raise HTTPException(422, "KIOSK_INVALID_ADDRESS")
        design = _clean_design(payload.design)

        def apply(state):
            kiosks = state["stationKiosks"]
            kiosk = kiosks.get(slug)
            if kiosk is None:
                if payload.revision != 0:
                    raise HTTPException(409, "KIOSK_DRAFT_CHANGED")
                kiosk = kiosks[slug] = {"revision": 0, "published": 0, "published_revision": 0,
                                       "versions": {}, "active": None, "completed": {}}
            if kiosk.get("draft") == design and kiosk["revision"] in {payload.revision, payload.revision + 1}:
                return _draft_view(slug, kiosk), False
            if kiosk["revision"] != payload.revision:
                raise HTTPException(409, "KIOSK_DRAFT_CHANGED")
            kiosk["draft"] = design
            kiosk["revision"] += 1
            return _draft_view(slug, kiosk), True

        return edit(apply)

    @router.post("/api/kiosk-designs/{slug}/publish", dependencies=[Depends(engineer), Depends(require_json)])
    def publish(slug: str, payload: Revision) -> dict[str, Any]:
        def apply(state):
            kiosk = _get_kiosk(state, slug)
            if kiosk["revision"] != payload.revision:
                raise HTTPException(409, "KIOSK_DRAFT_CHANGED")
            if not kiosk["draft"]["steps"]:
                raise HTTPException(422, "KIOSK_STEPS_REQUIRED")
            if kiosk["published_revision"] == payload.revision:
                return _draft_view(slug, kiosk), False
            kiosk["published"] += 1
            kiosk["published_revision"] = payload.revision
            kiosk["versions"][str(kiosk["published"])] = kiosk["draft"]
            return _draft_view(slug, kiosk), True

        return edit(apply)

    @router.get("/istasyon/{slug}")
    def operator_page(slug: str, request: Request) -> FileResponse:
        require_local(request)
        _get_kiosk(read_state(), slug, published=True)
        return FileResponse(templates / "station-kiosk.html", headers=html_headers)

    @router.get("/api/station-kiosks/{slug}")
    def operator_board(slug: str, request: Request) -> dict[str, Any]:
        require_local(request)
        return _board(read_state(), slug)

    @router.post("/api/station-kiosks/{slug}/start")
    def start_run(slug: str, payload: StartRun, request: Request) -> dict[str, Any]:
        require_local(request)
        require_json(request)
        operator = _text(payload.operator, 100, True)
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", payload.run_id):
            raise HTTPException(422, "KIOSK_INVALID_RUN")

        def apply(state):
            kiosk = _get_kiosk(state, slug, published=True)
            active = kiosk["active"]
            if active:
                if (active["run_id"], active["operator"], active["version"], active["order"]["id"], active["order"]["key"]) == (
                    payload.run_id, operator, payload.version, payload.order_id, payload.order_key
                ):
                    return _board(state, slug), False
                raise HTTPException(409, "KIOSK_RUN_ALREADY_OPEN")
            order = _current_order(state)
            if not order or (order["id"], order["key"], kiosk["published"]) != (payload.order_id, payload.order_key, payload.version):
                raise HTTPException(409, "KIOSK_START_CHANGED")
            if payload.run_id in kiosk["completed"]:
                raise HTTPException(409, "KIOSK_RUN_CHANGED")
            kiosk["active"] = {"run_id": payload.run_id, "operator": operator, "order": order,
                               "version": payload.version, "started_at": datetime.now(timezone.utc).isoformat()}
            return _board(state, slug), True

        return edit(apply)

    @router.post("/api/station-kiosks/{slug}/finish")
    def finish_run(slug: str, payload: FinishRun, request: Request) -> dict[str, Any]:
        require_local(request)
        require_json(request)

        def apply(state):
            kiosk = _get_kiosk(state, slug, published=True)
            previous = kiosk["completed"].get(payload.run_id)
            active = kiosk["active"]
            run = previous or active
            if not run or run["run_id"] != payload.run_id:
                raise HTTPException(409, "KIOSK_RUN_CHANGED")
            version = kiosk["versions"][str(run["version"])]
            values = _completed_values(payload.values, version, payload.result)
            if previous:
                if (previous["values"], previous["result"]) != (values, payload.result):
                    raise HTTPException(409, "KIOSK_RUN_CHANGED")
                return _board(state, slug), False
            kiosk["completed"][payload.run_id] = {**run, "values": values, "result": payload.result,
                                                   "finished_at": datetime.now(timezone.utc).isoformat()}
            kiosk["active"] = None
            return _board(state, slug), True

        return edit(apply)

    return router

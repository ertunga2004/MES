from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from secrets import compare_digest
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field, StrictBool, StrictInt, StrictStr, conint

from .manual_coating import manual_coating_order_key, manual_coating_progress


CARD_SOURCES = {
    "order": {"order"}, "instructions": {"fixed", "order"}, "steps": {"fixed"},
    "timer": {"fixed"}, "progress": {"fixed", "order"}, "result": {"fixed"},
    "status": {"station"}, "wip": {"station"}, "downtime": {"fixed"},
    "actions": {"fixed"}, "material": {"fixed", "station"}, "before": {"fixed"},
    "after": {"fixed"}, "extra": {"fixed"},
}

KIOSK_SLUG = re.compile(r"[a-z][a-z0-9-]{1,39}")
RESERVED_KIOSK_SLUGS = frozenset({
    "admin", "api", "bantlama", "calisan", "docs", "employee-observer", "giyotin",
    "health", "istasyon", "kaplama", "kiosk", "kiosk-tasarla", "muhendis", "mühendis",
    "operator", "operatör", "paketleme", "redoc", "static", "technician", "tekniker",
    "teknisyen", "ws", "yonetici", "yönetici",
})

PositiveQuantity = conint(strict=True, ge=1, le=1_000_000_000)
Quantity = conint(strict=True, ge=0, le=1_000_000_000)
NonnegativeInt = conint(strict=True, ge=0)


class Card(BaseModel):
    kind: StrictStr
    title: StrictStr = ""
    size: Literal["small", "medium", "large", "full"] = "medium"
    source: Literal["fixed", "station", "order"] = "fixed"
    visible: StrictBool = True
    body: StrictStr = ""


class Step(BaseModel):
    label: StrictStr
    kind: Literal["check", "text", "number", "choice"]
    required: StrictBool = True
    options: list[StrictStr] = Field(default_factory=list)
    interruptible: StrictBool = False


class Section(BaseModel):
    title: StrictStr
    body: StrictStr


class Design(BaseModel):
    title: StrictStr
    template: Literal["plain", "process", "quality", "packing", "material", "status"] = "plain"
    instructions: StrictStr = ""
    timer: StrictBool = False
    show_target: StrictBool = False
    result_options: list[StrictStr] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)
    sections: list[Section] = Field(default_factory=list)
    layout: Literal["single", "double", "sidebar"] | None = None
    shift_position: Literal["top", "compact"] = "top"
    station: Literal["", "cutting", "coating", "conveyor"] = ""
    cards: list[Card] | None = None
    before: StrictStr = ""
    after: StrictStr = ""
    target_quantity: PositiveQuantity | None = None
    target_unit: StrictStr = ""
    waiting_areas: list[StrictStr] = Field(default_factory=list)


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
    quantity: Quantity | None = None
    revision: NonnegativeInt | None = None


class UpdateRun(FinishRun):
    operation: Literal["save", "pause", "resume", "incident", "material-request", "park"]
    revision: NonnegativeInt
    note: StrictStr = ""
    amount: PositiveQuantity | None = None
    area: StrictStr = ""
    item: StrictStr = ""
    step_index: NonnegativeInt | None = None


class PickupRun(BaseModel):
    run_id: StrictStr
    operator: StrictStr


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
    if len(design.steps) > 30 or len(design.sections) > 20 or len(design.waiting_areas) > 10:
        raise HTTPException(422, "KIOSK_DESIGN_LIMIT")
    cards = None
    if design.cards is not None:
        kinds = {card.kind for card in design.cards}
        if len(kinds) != len(design.cards) or any(card.source not in CARD_SOURCES.get(card.kind, ()) for card in design.cards):
            raise HTTPException(422, "KIOSK_INVALID_CARD")
        cards = [
            {"kind": card.kind, "title": _text(card.title, 80), "size": card.size,
             "source": card.source, "visible": card.visible, "body": _text(card.body, 1500)}
            for card in design.cards
        ]
    return {
        "title": _text(design.title, 60, True),
        "template": design.template,
        "instructions": _text(design.instructions, 1500),
        "timer": design.timer, "show_target": design.show_target,
        "result_options": _options(design.result_options) if design.result_options else [],
        "steps": [
            {"label": _text(step.label, 100, True), "kind": step.kind, "required": step.required,
             "options": _options(step.options) if step.kind == "choice" else [],
             **({"interruptible": True} if step.interruptible else {})}
            for step in design.steps
        ],
        "sections": [{"title": _text(section.title, 80, True), "body": _text(section.body, 1500, True)} for section in design.sections],
        "layout": design.layout, "shift_position": design.shift_position, "station": design.station,
        "cards": cards, "before": _text(design.before, 1500), "after": _text(design.after, 1500),
        "target_quantity": design.target_quantity, "target_unit": _text(design.target_unit, 25),
        "waiting_areas": list(dict.fromkeys(_text(area, 80, True) for area in design.waiting_areas)),
    }


DESIGN_DEFAULTS = {
    "template": "plain", "layout": None, "shift_position": "top", "station": "",
    "cards": None, "before": "", "after": "", "target_quantity": None, "target_unit": "", "waiting_areas": [],
}


def _shows_card(design: dict[str, Any], kind: str) -> bool:
    cards = design.get("cards")
    return cards is None or any(card["kind"] == kind and card["visible"] for card in cards)


def _get_kiosk(state: dict[str, Any], slug: str, published: bool = False) -> dict[str, Any]:
    kiosk = state["stationKiosks"].get(slug)
    if not kiosk or (published and not kiosk["published"]):
        raise HTTPException(404, "KIOSK_NOT_FOUND")
    return kiosk


def _draft_view(slug: str, kiosk: dict[str, Any]) -> dict[str, Any]:
    completed = max(kiosk["completed"].values(), key=lambda run: run["finished_at"], default=None)
    path = f"/{slug}" if _has_short_path(slug) else f"/istasyon/{slug}"
    return {"slug": slug, "path": path, "draft": {**DESIGN_DEFAULTS, **kiosk["draft"]}, "revision": kiosk["revision"],
            "published": kiosk["published"], "published_revision": kiosk["published_revision"],
            "active": kiosk["active"], "last_completed": completed}


def _current_order(state: dict[str, Any]) -> dict[str, Any] | None:
    orders = state["workOrders"]
    order_id = orders["activeOrderId"]
    order = orders["ordersById"].get(order_id)
    if not order or order["status"] != "active":
        return None
    return {"id": order_id, "key": manual_coating_order_key(order), "quantity": order["quantity"], "unit": order["unit"] or "adet",
            "stock_code": order.get("stockCode", "")}


def _board(state: dict[str, Any], slug: str, cutting_enabled: bool = False) -> dict[str, Any]:
    kiosk = _get_kiosk(state, slug, published=True)
    active = kiosk["active"]
    version = active["version"] if active else kiosk["published"]
    design = {**DESIGN_DEFAULTS, **kiosk["versions"][str(version)]}
    order = active["order"] if active else _current_order(state)
    cutting = None
    if order and design["station"] in {"cutting", "coating"} and _shows_card(design, "wip"):
        progress = manual_coating_progress(state, cutting_enabled=cutting_enabled)
        if progress and (progress["order_id"], progress["order_key"]) == (order["id"], order["key"]):
            cutting = progress.get("cutting")
    parked = [
        {"run_id": run["run_id"], "order_id": run["order"]["id"], **run["park"]}
        for run in kiosk.get("parked", {}).values()
    ]
    return {"version": version, "design": design, "active": active, "order": order, "waiting": cutting, "parked": parked,
            "line_shift_active": state["shift"]["active"] if design["station"] == "conveyor" else None}


def _has_short_path(slug: str) -> bool:
    return slug not in RESERVED_KIOSK_SLUGS and KIOSK_SLUG.fullmatch(slug) is not None


def _observer_board(board: dict[str, Any]) -> dict[str, Any]:
    active = board["active"]
    order = board["order"]
    active_fields = ("operator", "started_at", "paused_at", "waiting_seconds", "values", "result", "quantity", "reports")
    return {
        **board,
        "active": {field: active[field] for field in active_fields if field in active} if active else None,
        "order": {field: value for field, value in order.items() if field != "key"} if order else None,
        "parked": [{field: value for field, value in row.items() if field != "run_id"} for row in board["parked"]],
    }


def _completed_values(values: list[Any], design: dict[str, Any], result: str, *, finishing: bool = True) -> list[Any]:
    steps = design["steps"] if _shows_card(design, "steps") else []
    if len(values) != len(steps):
        raise HTTPException(422, "KIOSK_INVALID_STEPS")
    checked = []
    for step, value in zip(steps, values):
        kind = step["kind"]
        required = finishing and step["required"]
        if kind == "check":
            valid = type(value) is bool and (value or not required)
        elif value is None:
            valid = not required
        elif kind == "number":
            valid = type(value) in (int, float) and -1e12 <= value <= 1e12 and math.isfinite(value)
        elif kind == "choice":
            valid = value in step["options"]
        else:
            valid = isinstance(value, str) and len(value) <= 500 and (bool(value.strip()) or not required)
        if not valid:
            raise HTTPException(422, "KIOSK_INVALID_STEP_VALUE")
        checked.append(value.strip() if isinstance(value, str) else value)
    options = design["result_options"] if _shows_card(design, "result") else []
    if (result and result not in options) or (finishing and options and not result):
        raise HTTPException(422, "KIOSK_INVALID_RESULT")
    return checked


def create_kiosk_router(static_dir, get_context, require_local, require_operator=None) -> APIRouter:
    router = APIRouter()
    operator_access = require_operator if require_operator is not None else require_local
    basic = HTTPBasic(auto_error=False, realm="MES Kiosk Tasarla")
    templates = static_dir.parent / "templates"
    html_headers = {"Cache-Control": "no-store", "Content-Security-Policy": "frame-ancestors 'none'"}
    observer_headers = {"Cache-Control": "no-store", "Content-Security-Policy": "frame-ancestors 'self'"}

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

    def board(state, slug):
        return _board(state, slug, get_context()[0].cutting_workflow_enabled)

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
        if not KIOSK_SLUG.fullmatch(slug):
            raise HTTPException(422, "KIOSK_INVALID_ADDRESS")
        design = _clean_design(payload.design)

        def apply(state):
            kiosks = state["stationKiosks"]
            kiosk = kiosks.get(slug)
            if kiosk is None:
                if not _has_short_path(slug):
                    raise HTTPException(422, "KIOSK_INVALID_ADDRESS")
                if payload.revision != 0:
                    raise HTTPException(409, "KIOSK_DRAFT_CHANGED")
                kiosk = kiosks[slug] = {"revision": 0, "published": 0, "published_revision": 0,
                                       "versions": {}, "active": None, "completed": {}}
            previous = kiosk.get("draft")
            if previous is not None and {**DESIGN_DEFAULTS, **previous} == design and kiosk["revision"] in {payload.revision, payload.revision + 1}:
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
            if _shows_card(kiosk["draft"], "steps") and not kiosk["draft"]["steps"]:
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
        operator_access(request)
        _get_kiosk(read_state(), slug, published=True)
        return FileResponse(templates / "station-kiosk.html", headers=html_headers)

    @router.get("/calisan/kiosk/{slug}")
    def observer_page(slug: str, request: Request) -> FileResponse:
        require_local(request)
        _get_kiosk(read_state(), slug, published=True)
        return FileResponse(templates / "station-kiosk.html", headers=observer_headers)

    @router.get("/api/employee-observer/kiosks")
    def observer_catalog(request: Request) -> list[dict[str, str]]:
        require_local(request)
        return [
            {"slug": slug, "title": kiosk["versions"][str(kiosk["published"])]["title"], "path": f"/calisan/kiosk/{slug}"}
            for slug, kiosk in sorted(read_state()["stationKiosks"].items()) if kiosk["published"]
        ]

    @router.get("/api/employee-observer/kiosks/{slug}")
    def observer_board(slug: str, request: Request) -> dict[str, Any]:
        require_local(request)
        return _observer_board(board(read_state(), slug))

    @router.get("/api/station-kiosks/{slug}")
    def operator_board(slug: str, request: Request) -> dict[str, Any]:
        operator_access(request)
        return board(read_state(), slug)

    @router.post("/api/station-kiosks/{slug}/start")
    def start_run(slug: str, payload: StartRun, request: Request) -> dict[str, Any]:
        operator_access(request)
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
                    return board(state, slug), False
                raise HTTPException(409, "KIOSK_RUN_ALREADY_OPEN")
            order = _current_order(state)
            if not order or (order["id"], order["key"], kiosk["published"]) != (payload.order_id, payload.order_key, payload.version):
                raise HTTPException(409, "KIOSK_START_CHANGED")
            if payload.run_id in kiosk["completed"] or payload.run_id in kiosk.get("parked", {}):
                raise HTTPException(409, "KIOSK_RUN_CHANGED")
            kiosk["active"] = {"run_id": payload.run_id, "operator": operator, "order": order,
                               "version": payload.version, "started_at": datetime.now(timezone.utc).isoformat()}
            return board(state, slug), True

        return edit(apply)

    @router.post("/api/station-kiosks/{slug}/update")
    def update_run(slug: str, payload: UpdateRun, request: Request) -> dict[str, Any]:
        operator_access(request)
        require_json(request)

        def apply(state):
            kiosk = _get_kiosk(state, slug, published=True)
            run = kiosk["active"]
            if not run or run["run_id"] != payload.run_id or run.get("revision", 0) != payload.revision:
                raise HTTPException(409, "KIOSK_RUN_CHANGED")
            design = kiosk["versions"][str(run["version"])]
            values = _completed_values(payload.values, design, payload.result, finishing=False)
            now = datetime.now(timezone.utc)
            operation = payload.operation
            if operation in {"pause", "resume"}:
                if not design["timer"] or not _shows_card(design, "timer"):
                    raise HTTPException(422, "KIOSK_TIMER_DISABLED")
                paused_at = run.get("paused_at")
                if operation == "pause" and not paused_at:
                    run["paused_at"] = now.isoformat()
                if operation == "resume" and paused_at:
                    run["waiting_seconds"] = run.get("waiting_seconds", 0) + (now - datetime.fromisoformat(paused_at)).total_seconds()
                    run["paused_at"] = None
            if operation in {"incident", "material-request"}:
                kind = "downtime" if operation == "incident" else "material"
                if design.get("cards") is None or not _shows_card(design, kind):
                    raise HTTPException(422, "KIOSK_CARD_DISABLED")
                note = _text(payload.note, 300 if kind == "downtime" else 80, True)
                if kind == "material" and payload.amount is None:
                    raise HTTPException(422, "KIOSK_INVALID_QUANTITY")
                reports = run.setdefault("reports", [])
                if len(reports) >= 100:
                    raise HTTPException(422, "KIOSK_REPORT_LIMIT")
                reports.append({"kind": kind, "note": note, "amount": payload.amount, "at": now.isoformat()})
            run.update(values=values, result=payload.result, quantity=payload.quantity, revision=payload.revision + 1)
            if operation == "park":
                area = _text(payload.area, 80, True)
                item = _text(payload.item, 100, True)
                note = _text(payload.note, 300, True)
                steps = design["steps"]
                index = payload.step_index
                if not _shows_card(design, "wip") or not _shows_card(design, "steps") or area not in design.get("waiting_areas", ()):
                    raise HTTPException(422, "KIOSK_WAITING_AREA_DISABLED")
                if index is None or index >= len(steps) or not steps[index].get("interruptible"):
                    raise HTTPException(422, "KIOSK_WAITING_STEP_REQUIRED")
                if any(step["required"] and (value is None or value is False or value == "")
                       for step, value in zip(steps[:index], values[:index])):
                    raise HTTPException(422, "KIOSK_WAITING_STEP_REQUIRED")
                parked = kiosk.setdefault("parked", {})
                if len(parked) >= 100 or len(run.get("park_history", [])) >= 100 or any(
                    saved["park"]["item"] == item for saved in parked.values()
                ):
                    raise HTTPException(409, "KIOSK_WAITING_ITEM_CONFLICT")
                run["paused_at"] = run.get("paused_at") or now.isoformat()
                run["park"] = {"area": area, "item": item, "note": note, "at": now.isoformat(), "operator": run["operator"]}
                parked[run["run_id"]] = run
                kiosk["active"] = None
            return board(state, slug), True

        return edit(apply)

    @router.post("/api/station-kiosks/{slug}/pickup")
    def pickup_run(slug: str, payload: PickupRun, request: Request) -> dict[str, Any]:
        operator_access(request)
        require_json(request)
        operator = _text(payload.operator, 100, True)

        def apply(state):
            kiosk = _get_kiosk(state, slug, published=True)
            active = kiosk["active"]
            if active and active["run_id"] == payload.run_id and active["operator"] == operator:
                return board(state, slug), False
            parked = kiosk.get("parked", {})
            if active or payload.run_id not in parked:
                raise HTTPException(409, "KIOSK_RUN_CHANGED")
            run = parked.pop(payload.run_id)
            run.setdefault("park_history", []).append(run.pop("park"))
            waited = datetime.now(timezone.utc) - datetime.fromisoformat(run.pop("paused_at"))
            run["waiting_seconds"] = run.get("waiting_seconds", 0) + waited.total_seconds()
            run.update(operator=operator, revision=run["revision"] + 1)
            kiosk["active"] = run
            return board(state, slug), True

        return edit(apply)

    @router.post("/api/station-kiosks/{slug}/finish")
    def finish_run(slug: str, payload: FinishRun, request: Request) -> dict[str, Any]:
        operator_access(request)
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
                if (previous["values"], previous["result"], previous.get("quantity")) != (values, payload.result, payload.quantity):
                    raise HTTPException(409, "KIOSK_RUN_CHANGED")
                return board(state, slug), False
            if run.get("revision", 0) != (payload.revision or 0):
                raise HTTPException(409, "KIOSK_RUN_CHANGED")
            kiosk["completed"][payload.run_id] = {**run, "values": values, "result": payload.result,
                                                   "quantity": payload.quantity,
                                                   "finished_at": datetime.now(timezone.utc).isoformat()}
            kiosk["active"] = None
            return board(state, slug), True

        return edit(apply)

    return router


def create_kiosk_alias_router(static_dir, get_context, require_local, require_operator=None) -> APIRouter:
    """Include after the fixed application routes so an alias never shadows them."""
    router = APIRouter()
    operator_access = require_operator if require_operator is not None else require_local
    template = static_dir.parent / "templates" / "station-kiosk.html"
    headers = {"Cache-Control": "no-store", "Content-Security-Policy": "frame-ancestors 'none'"}

    @router.get("/{slug}", include_in_schema=False)
    def operator_alias(slug: str, request: Request) -> FileResponse:
        if not _has_short_path(slug):
            raise HTTPException(404, "KIOSK_NOT_FOUND")
        operator_access(request)
        _get_kiosk(get_context()[1].read_state(), slug, published=True)
        return FileResponse(template, headers=headers)

    return router

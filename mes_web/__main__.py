from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

from .db import mesql_v2


STATION_LOCATION_READ_MODEL_FEATURE_FLAG = "MES_WEB_DB_STATION_LOCATION_READ_MODEL_ENABLED"
ALLOWED_LOCATION_TYPES = frozenset({
    "raw_material",
    "wip",
    "buffer",
    "finished_goods",
    "scrap",
    "hold",
    "rework",
})
ALLOWED_BINDING_ROLES = frozenset({
    "input",
    "active_wip",
    "output_good",
    "output_scrap",
    "output_buffer",
})


def _configure_event_loop_policy() -> None:
    if sys.platform != "win32":
        return
    selector_policy_cls = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if selector_policy_cls is None:
        return
    current_policy = asyncio.get_event_loop_policy()
    if not isinstance(current_policy, selector_policy_cls):
        asyncio.set_event_loop_policy(selector_policy_cls())


def _station_location_read_model_enabled() -> bool:
    raw = os.getenv(STATION_LOCATION_READ_MODEL_FEATURE_FLAG, "")
    return raw.strip().lower() in {"true", "1", "yes", "on"}


def _normalize_code(value: str) -> str:
    return str(value or "").strip().upper()


def _normalize_optional_filter(value: str | None, *, allowed: frozenset[str], error_code: str) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if not normalized:
        return None
    if normalized not in allowed:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=error_code)
    return normalized


def _parse_active_only(value: str | bool | None) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if not normalized:
        return True
    if normalized in {"true", "1"}:
        return True
    if normalized in {"false", "0"}:
        return False
    from fastapi import HTTPException

    raise HTTPException(status_code=400, detail="INVALID_QUERY_PARAM")


def register_station_location_read_routes(app: Any, app_config: Any) -> None:
    from fastapi import HTTPException, Query

    def require_enabled() -> None:
        if not _station_location_read_model_enabled():
            raise HTTPException(status_code=503, detail="STATION_LOCATION_READ_MODEL_DISABLED")

    def raise_mesql_v2_error(exc: mesql_v2.MesqlV2Error) -> None:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    @app.get("/api/v2/locations")
    async def api_v2_locations(
        active_only: str | None = Query(default=None),
        location_type: str | None = Query(default=None),
    ) -> dict[str, Any]:
        require_enabled()
        parsed_active_only = _parse_active_only(active_only)
        normalized_location_type = _normalize_optional_filter(
            location_type,
            allowed=ALLOWED_LOCATION_TYPES,
            error_code="INVALID_LOCATION_TYPE",
        )
        try:
            locations = mesql_v2.list_locations(
                app_config,
                active_only=parsed_active_only,
                location_type=normalized_location_type,
            )
        except mesql_v2.MesqlV2Error as exc:
            raise_mesql_v2_error(exc)
        return {"ok": True, "data": locations, "count": len(locations)}

    @app.get("/api/v2/locations/{location_code}")
    async def api_v2_location_detail(location_code: str) -> dict[str, Any]:
        require_enabled()
        normalized_location_code = _normalize_code(location_code)
        try:
            location = mesql_v2.get_location_by_code(app_config, normalized_location_code)
        except mesql_v2.MesqlV2Error as exc:
            raise_mesql_v2_error(exc)
        if location is None:
            raise HTTPException(status_code=404, detail="LOCATION_NOT_FOUND")
        return {"ok": True, "data": location}

    @app.get("/api/v2/stations/{station_code}/locations")
    async def api_v2_station_locations(
        station_code: str,
        active_only: str | None = Query(default=None),
        role: str | None = Query(default=None),
    ) -> dict[str, Any]:
        require_enabled()
        normalized_station_code = _normalize_code(station_code)
        parsed_active_only = _parse_active_only(active_only)
        normalized_role = _normalize_optional_filter(
            role,
            allowed=ALLOWED_BINDING_ROLES,
            error_code="INVALID_BINDING_ROLE",
        )
        try:
            bindings = mesql_v2.list_station_location_bindings(
                app_config,
                normalized_station_code,
                active_only=parsed_active_only,
                role=normalized_role,
            )
        except mesql_v2.MesqlV2Error as exc:
            raise_mesql_v2_error(exc)
        return {
            "ok": True,
            "station_code": normalized_station_code,
            "data": bindings,
            "count": len(bindings),
        }

    @app.get("/api/v2/stations/{station_code}/location-context")
    async def api_v2_station_location_context(station_code: str) -> dict[str, Any]:
        require_enabled()
        normalized_station_code = _normalize_code(station_code)
        try:
            context = mesql_v2.get_station_location_context(app_config, normalized_station_code)
        except mesql_v2.MesqlV2Error as exc:
            raise_mesql_v2_error(exc)
        return {
            "ok": True,
            "station_code": normalized_station_code,
            "data": context,
        }


def main() -> None:
    _configure_event_loop_policy()
    try:
        import uvicorn
        from .app import app, config
    except ModuleNotFoundError as exc:
        raise SystemExit(f"Missing dependency: {exc.name}. Install mes_web/requirements.txt first.") from exc

    register_station_location_read_routes(app, config)
    uvicorn.run(app, host=config.host, port=config.port, reload=False)


if __name__ == "__main__":
    main()
